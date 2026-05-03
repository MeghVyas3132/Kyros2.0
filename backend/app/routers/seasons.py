from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import (
    AllocationSession,
    AllocationStatus,
    BuyPlanFile,
    BuyPlanLine,
    GRN,
    SalesData,
    Season,
    SeasonOTB,
    SeasonStatus,
    SKU,
    StoreProductGrade,
    User,
    UserRole,
)
from app.routers._helpers import envelope
from app.schemas.season import OTBInput, SeasonCreate, SeasonUpdate
from app.services.llm.narration import narrate_otb_suggestion
from app.services.workflow_state import advance_season_if_earlier
from datetime import date as _date_type

from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/seasons", tags=["seasons"])


@router.get("")
async def list_seasons(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    rows = (await db.execute(select(Season).where(Season.brand_id == current_user.brand_id))).scalars().all()
    return envelope(rows)


@router.post("")
async def create_season(
    payload: SeasonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = Season(brand_id=current_user.brand_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.put("/{season_id}")
async def update_season(
    season_id: UUID,
    payload: SeasonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = await db.get(Season, season_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Season not found"})

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.get("/{season_id}/otb")
async def get_otb(
    season_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = (
        await db.execute(
            select(SeasonOTB).where(
                SeasonOTB.brand_id == current_user.brand_id, SeasonOTB.season_id == season_id
            )
        )
    ).scalars().all()
    return envelope(rows)


@router.post("/{season_id}/otb")
async def save_otb(
    season_id: UUID,
    payload: list[OTBInput],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    season = await db.get(Season, season_id)
    if season is None or season.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Season not found"})

    for row in payload:
        existing = await db.execute(
            select(SeasonOTB).where(
                SeasonOTB.brand_id == current_user.brand_id,
                SeasonOTB.season_id == season_id,
                SeasonOTB.category == row.category,
                SeasonOTB.month == row.month,
            )
        )
        item = existing.scalar_one_or_none()
        if item is None:
            db.add(
                SeasonOTB(
                    season_id=season_id,
                    brand_id=current_user.brand_id,
                    category=row.category,
                    month=row.month,
                    planned_sales=row.planned_sales,
                    planned_closing_stock=row.planned_closing_stock,
                    opening_stock=row.opening_stock,
                    on_order=row.on_order,
                )
            )
        else:
            item.planned_sales = row.planned_sales
            item.planned_closing_stock = row.planned_closing_stock
            item.opening_stock = row.opening_stock
            item.on_order = row.on_order

    # Saving any OTB row counts as exiting DRAFT.
    await advance_season_if_earlier(
        db,
        brand_id=current_user.brand_id,
        season_id=season_id,
        target=SeasonStatus.PLANNING,
    )
    await db.commit()
    return envelope({"saved": len(payload)})


class OTBSuggestRequest(BaseModel):
    growth_factor: float = Field(default=1.10, ge=0.5, le=3.0)


@router.post("/{season_id}/otb/suggest")
async def suggest_otb(
    season_id: UUID,
    payload: OTBSuggestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    """History-driven OTB suggestion.

    Aggregates SalesData revenue by category × calendar month, multiplies by
    `growth_factor`, and returns a per-category suggestion with an
    LLM-narrated explanation. Does NOT write anything — the planner has to
    explicitly accept and POST to /otb."""
    season = await db.get(Season, season_id)
    if season is None or season.brand_id != current_user.brand_id:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "Season not found"}
        )

    # Sum revenue per category from sales_data joined with skus.
    # Group by category only — we don't have a reliable way to map weeks
    # of last season to months of next season, so aggregate annualised.
    rows = (
        await db.execute(
            select(
                SKU.category,
                func.coalesce(func.sum(SalesData.revenue), 0).label("revenue"),
                func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
            )
            .join(SKU, SKU.id == SalesData.sku_id)
            .where(
                SalesData.brand_id == current_user.brand_id,
                SKU.category.is_not(None),
            )
            .group_by(SKU.category)
            .order_by(func.sum(SalesData.revenue).desc())
        )
    ).all()

    growth = float(payload.growth_factor)
    suggestions: list[dict] = []

    for row in rows:
        cat = row.category
        last_revenue = float(row.revenue or 0)
        last_units = int(row.units or 0)
        suggested = round(last_revenue * growth, 2)
        facts = {
            "category": cat,
            "last_season_actual_sales": round(last_revenue, 2),
            "last_season_actual_units": last_units,
            "growth_factor": growth,
            "suggested_planned_sales": suggested,
        }
        narration = await narrate_otb_suggestion(facts)
        suggestions.append(
            {
                "category": cat,
                "last_actual_revenue": round(last_revenue, 2),
                "last_actual_units": last_units,
                "growth_factor": growth,
                "suggested_planned_sales": suggested,
                "narration": narration,
            }
        )

    total_last = sum(s["last_actual_revenue"] for s in suggestions)
    total_suggested = sum(s["suggested_planned_sales"] for s in suggestions)

    return envelope(
        {
            "season_id": str(season_id),
            "growth_factor": growth,
            "categories": suggestions,
            "totals": {
                "last_actual_revenue": round(total_last, 2),
                "suggested_planned_sales": round(total_suggested, 2),
            },
            "note": (
                "Suggestions are seeded from last-season actuals × growth factor. "
                "They are not saved until you POST them to /otb."
            ),
        }
    )


@router.get("/{season_id}/otb/summary")
async def get_otb_summary(
    season_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    season = await db.get(Season, season_id)
    if season is None or season.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Season not found"})

    # Fetch all OTB rows for this season
    otb_rows = (
        await db.execute(
            select(SeasonOTB).where(
                SeasonOTB.season_id == season_id,
                SeasonOTB.brand_id == current_user.brand_id,
            )
        )
    ).scalars().all()

    # Compute committed cost per category from BuyPlanLines
    committed_result = await db.execute(
        select(
            SKU.category,
            func.coalesce(
                func.sum(BuyPlanLine.planned_cost_per_unit * BuyPlanLine.total_buy_qty), 0
            ).label("committed_cost"),
        )
        .join(BuyPlanFile, BuyPlanFile.id == BuyPlanLine.buy_plan_file_id)
        .join(SKU, SKU.id == BuyPlanLine.sku_id)
        .where(
            BuyPlanFile.season_id == season_id,
            BuyPlanFile.brand_id == current_user.brand_id,
        )
        .group_by(SKU.category)
    )
    committed_by_category: dict[str, float] = {
        row.category: float(row.committed_cost) for row in committed_result.all() if row.category
    }

    # Derive categories and months from OTB rows
    categories: list[str] = sorted({r.category for r in otb_rows})
    months: list[str] = sorted({str(r.month) for r in otb_rows})

    # Count months per category for spreading committed cost
    months_per_category: dict[str, int] = {}
    for r in otb_rows:
        months_per_category[r.category] = months_per_category.get(r.category, 0) + 1

    rows = []
    for r in otb_rows:
        otb_val = float(r.otb_value) if r.otb_value is not None else 0.0
        cat_committed = committed_by_category.get(r.category, 0.0)
        month_count = months_per_category.get(r.category, 1) or 1
        committed_this_month = cat_committed / month_count
        delta = otb_val - committed_this_month
        usage_pct = round((committed_this_month / otb_val * 100) if otb_val > 0 else 0.0, 2)
        rows.append({
            "category": r.category,
            "month": str(r.month),
            "planned_sales": float(r.planned_sales),
            "opening_stock": float(r.opening_stock),
            "planned_closing_stock": float(r.planned_closing_stock),
            "on_order": float(r.on_order),
            "otb_value": otb_val,
            "committed_cost": round(committed_this_month, 2),
            "delta": round(delta, 2),
            "usage_pct": usage_pct,
        })

    total_otb = sum(float(r.otb_value) for r in otb_rows if r.otb_value is not None)
    total_committed = sum(committed_by_category.values())
    overall_usage_pct = round((total_committed / total_otb * 100) if total_otb > 0 else 0.0, 2)

    return envelope({
        "season_id": str(season_id),
        "categories": categories,
        "months": months,
        "rows": rows,
        "totals": {
            "total_otb": round(total_otb, 2),
            "total_committed": round(total_committed, 2),
            "overall_usage_pct": overall_usage_pct,
        },
    })


@router.get("/{season_id}/otb/reconciliation")
async def get_otb_reconciliation(
    season_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    season = await db.get(Season, season_id)
    if season is None or season.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Season not found"})

    # OTB per category
    otb_result = await db.execute(
        select(
            SeasonOTB.category,
            func.coalesce(func.sum(SeasonOTB.otb_value), 0).label("total_otb"),
        )
        .where(
            SeasonOTB.season_id == season_id,
            SeasonOTB.brand_id == current_user.brand_id,
        )
        .group_by(SeasonOTB.category)
    )
    otb_by_category: dict[str, float] = {row.category: float(row.total_otb) for row in otb_result.all()}

    # Committed cost per category
    committed_result = await db.execute(
        select(
            SKU.category,
            func.coalesce(
                func.sum(BuyPlanLine.planned_cost_per_unit * BuyPlanLine.total_buy_qty), 0
            ).label("committed_cost"),
        )
        .join(BuyPlanFile, BuyPlanFile.id == BuyPlanLine.buy_plan_file_id)
        .join(SKU, SKU.id == BuyPlanLine.sku_id)
        .where(
            BuyPlanFile.season_id == season_id,
            BuyPlanFile.brand_id == current_user.brand_id,
        )
        .group_by(SKU.category)
    )
    committed_by_category: dict[str, float] = {
        row.category: float(row.committed_cost) for row in committed_result.all() if row.category
    }

    all_categories = sorted(set(list(otb_by_category.keys()) + list(committed_by_category.keys())))
    reconciliation_rows = []
    overrun_categories = []

    for cat in all_categories:
        total_otb = otb_by_category.get(cat, 0.0)
        total_committed = committed_by_category.get(cat, 0.0)
        usage_pct = round((total_committed / total_otb * 100) if total_otb > 0 else 0.0, 2)
        is_overrun = total_committed > total_otb
        delta = total_otb - total_committed
        if is_overrun:
            overrun_categories.append(cat)
        reconciliation_rows.append({
            "category": cat,
            "total_otb": round(total_otb, 2),
            "total_committed": round(total_committed, 2),
            "usage_pct": usage_pct,
            "is_overrun": is_overrun,
            "delta": round(delta, 2),
        })

    grand_otb = sum(otb_by_category.values())
    grand_committed = sum(committed_by_category.values())
    overall_usage_pct = round((grand_committed / grand_otb * 100) if grand_otb > 0 else 0.0, 2)

    return envelope({
        "season_id": str(season_id),
        "rows": reconciliation_rows,
        "overrun_categories": overrun_categories,
        "has_overruns": len(overrun_categories) > 0,
        "total_otb": round(grand_otb, 2),
        "total_committed": round(grand_committed, 2),
        "overall_usage_pct": overall_usage_pct,
    })


@router.get("/{season_id}/workflow-state")
async def get_workflow_state(
    season_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    season = await db.get(Season, season_id)
    if season is None or season.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Season not found"})

    # Step 2: OTB Budget — SeasonOTB rows exist
    otb_count = await db.scalar(
        select(func.count(SeasonOTB.id)).where(
            SeasonOTB.season_id == season_id,
            SeasonOTB.brand_id == current_user.brand_id,
        )
    ) or 0

    # Step 3: Data Uploaded — SalesData rows exist for this brand AND StoreProductGrade rows exist
    sales_count = await db.scalar(
        select(func.count(SalesData.id)).where(SalesData.brand_id == current_user.brand_id)
    ) or 0
    grade_count = await db.scalar(
        select(func.count(StoreProductGrade.id)).where(StoreProductGrade.brand_id == current_user.brand_id)
    ) or 0

    # Step 4: Buy Plan — BuyPlanFile with season_id exists
    buy_plan_count = await db.scalar(
        select(func.count(BuyPlanFile.id)).where(
            BuyPlanFile.season_id == season_id,
            BuyPlanFile.brand_id == current_user.brand_id,
        )
    ) or 0

    # Step 5: Stock Received — GRN with season_id exists
    grn_count = await db.scalar(
        select(func.count(GRN.id)).where(
            GRN.season_id == season_id,
            GRN.brand_id == current_user.brand_id,
        )
    ) or 0

    # Step 6: Allocation Done — AllocationSession with season_id and APPROVED or DISPATCHED status
    allocation_count = await db.scalar(
        select(func.count(AllocationSession.id)).where(
            AllocationSession.season_id == season_id,
            AllocationSession.brand_id == current_user.brand_id,
            AllocationSession.status.in_([AllocationStatus.APPROVED, AllocationStatus.DISPATCHED]),
        )
    ) or 0

    step_complete = {
        1: True,  # Season Setup: always complete if season exists
        2: int(otb_count) > 0,
        3: int(sales_count) > 0 and int(grade_count) > 0,
        4: int(buy_plan_count) > 0,
        5: int(grn_count) > 0,
        6: int(allocation_count) > 0,
    }

    step_meta = [
        (1, "Season Setup", "Create the season and set dates", "/setup/seasons", "Configure Season"),
        (2, "OTB Budget", "Set your Open-To-Buy budget per category", "/setup/seasons", "Set OTB Budget"),
        (3, "Data Uploaded", "Upload sales history and store grades", "/ingestion", "Upload Data"),
        (4, "Buy Plan", "Create and submit your buy plan", "/buy-plan", "Create Buy Plan"),
        (5, "Stock Received", "Record goods received from vendors", "/grn", "Record Stock"),
        (6, "Allocation Done", "Generate and approve store allocations", "/allocation", "Run Allocation"),
    ]

    # Determine current step: first incomplete step
    current_step = 6
    for step_num, _, _, _, _ in step_meta:
        if not step_complete[step_num]:
            current_step = step_num
            break

    all_complete = all(step_complete.values())
    if all_complete:
        current_step = 6

    steps = []
    for step_num, label, description, action_url, action_label in step_meta:
        is_complete = step_complete[step_num]
        is_current = step_num == current_step and not is_complete
        is_blocked = step_num > current_step and not is_complete
        steps.append({
            "step": step_num,
            "label": label,
            "description": description,
            "is_complete": is_complete,
            "is_current": is_current,
            "is_blocked": is_blocked,
            "action_label": action_label if is_current else None,
            "action_url": action_url if is_current else None,
        })

    next_incomplete = next((s for s in steps if not s["is_complete"]), None)
    next_step = (
        {
            "step": next_incomplete["step"],
            "label": next_incomplete["label"],
            "action_label": next_incomplete["action_label"] or "",
            "action_url": next_incomplete["action_url"] or "",
        }
        if next_incomplete
        else None
    )

    return envelope({
        "season_id": str(season_id),
        "season_name": season.name,
        "current_status": season.status.value if isinstance(season.status, SeasonStatus) else str(season.status),
        "current_step": current_step,
        "total_steps": 6,
        "steps": steps,
        "next_step": next_step,
    })
