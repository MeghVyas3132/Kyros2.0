from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete as delete_stmt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import BuyPlanFile, BuyPlanLine, Season, SeasonOTB, SeasonStatus, User, UserRole
from app.models.sku import SKU
from app.services.workflow_state import advance_season_if_earlier
from app.routers._helpers import envelope
from app.schemas.buy_plan import (
    BuyPlanCreate,
    BuyPlanLineCreate,
    BuyPlanLineUpdate,
    BuyPlanUpdate,
)

router = APIRouter(prefix="/api/v1/buy-plans", tags=["buy-plans"])


def _serialize_line(line: BuyPlanLine, sku: SKU | None) -> dict:
    return {
        "id": str(line.id),
        "buy_plan_file_id": str(line.buy_plan_file_id),
        "brand_id": str(line.brand_id),
        "sku_id": str(line.sku_id),
        "sku_code": sku.sku_code if sku else None,
        "style_code": sku.style_code if sku else None,
        "style_name": sku.style_name if sku else None,
        "category": sku.category if sku else None,
        "size": sku.size if sku else None,
        "colour": sku.colour if sku else None,
        "price_band": sku.price_band if sku else None,
        "store_group_rule": line.store_group_rule,
        "style_risk_group": line.style_risk_group,
        "total_buy_qty": line.total_buy_qty,
        "expected_first_allocation_qty": line.expected_first_allocation_qty,
        "vendor_name": line.vendor_name,
        "expected_delivery_week": line.expected_delivery_week.isoformat() if line.expected_delivery_week else None,
        "planned_cost_per_unit": float(line.planned_cost_per_unit) if line.planned_cost_per_unit is not None else None,
        "moq": line.moq,
        "planned_price_per_unit": float(line.planned_price_per_unit) if line.planned_price_per_unit is not None else None,
        "planned_margin_pct": float(line.planned_margin_pct) if line.planned_margin_pct is not None else None,
        "created_at": line.created_at.isoformat(),
        "updated_at": line.updated_at.isoformat(),
    }


def _serialize_plan(f: BuyPlanFile) -> dict:
    return {
        "id": str(f.id),
        "brand_id": str(f.brand_id),
        "season_id": str(f.season_id) if f.season_id else None,
        "name": f.name,
        "source_filename": f.source_filename,
        "notes": f.notes,
        "created_at": f.created_at.isoformat(),
        "updated_at": f.updated_at.isoformat(),
    }


async def _validate_season_or_404(
    db: AsyncSession, brand_id: UUID, season_id: UUID | None
) -> None:
    if season_id is None:
        return
    season = await db.get(Season, season_id)
    if season is None or season.brand_id != brand_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Season not found for this brand"},
        )


async def _get_plan_or_404(
    db: AsyncSession, brand_id: UUID, file_id: UUID
) -> BuyPlanFile:
    plan = await db.get(BuyPlanFile, file_id)
    if plan is None or plan.brand_id != brand_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Buy plan not found"},
        )
    return plan


async def _validate_sku_or_404(db: AsyncSession, brand_id: UUID, sku_id: UUID) -> SKU:
    sku = await db.get(SKU, sku_id)
    if sku is None or sku.brand_id != brand_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "SKU not found for this brand"},
        )
    return sku


@router.get("")
async def list_buy_plans(
    season_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    stmt = select(BuyPlanFile).where(BuyPlanFile.brand_id == current_user.brand_id)
    if season_id is not None:
        stmt = stmt.where(BuyPlanFile.season_id == season_id)
    stmt = stmt.order_by(BuyPlanFile.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()

    result = []
    for f in rows:
        total_lines = await db.scalar(
            select(func.count(BuyPlanLine.id)).where(BuyPlanLine.buy_plan_file_id == f.id)
        ) or 0
        total_units = await db.scalar(
            select(func.coalesce(func.sum(BuyPlanLine.total_buy_qty), 0)).where(
                BuyPlanLine.buy_plan_file_id == f.id
            )
        ) or 0
        # distinct style_codes via join with SKU
        total_styles_row = await db.execute(
            select(func.count(func.distinct(SKU.style_code))).join(
                BuyPlanLine, BuyPlanLine.sku_id == SKU.id
            ).where(BuyPlanLine.buy_plan_file_id == f.id)
        )
        total_styles = total_styles_row.scalar() or 0

        categories_rows = await db.execute(
            select(func.distinct(SKU.category)).join(
                BuyPlanLine, BuyPlanLine.sku_id == SKU.id
            ).where(BuyPlanLine.buy_plan_file_id == f.id).order_by(SKU.category)
        )
        categories = [r[0] for r in categories_rows.all() if r[0]]

        result.append({
            "id": str(f.id),
            "brand_id": str(f.brand_id),
            "season_id": str(f.season_id) if f.season_id else None,
            "name": f.name,
            "source_filename": f.source_filename,
            "notes": f.notes,
            "created_at": f.created_at.isoformat(),
            "updated_at": f.updated_at.isoformat(),
            "total_lines": int(total_lines),
            "total_units": int(total_units),
            "total_styles": int(total_styles),
            "categories": categories,
        })

    return envelope(result)


@router.get("/{file_id}")
async def get_buy_plan(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    f = await db.get(BuyPlanFile, file_id)
    if f is None or f.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Buy plan not found"})

    total_lines = await db.scalar(
        select(func.count(BuyPlanLine.id)).where(BuyPlanLine.buy_plan_file_id == f.id)
    ) or 0
    total_units = await db.scalar(
        select(func.coalesce(func.sum(BuyPlanLine.total_buy_qty), 0)).where(
            BuyPlanLine.buy_plan_file_id == f.id
        )
    ) or 0
    total_styles_row = await db.execute(
        select(func.count(func.distinct(SKU.style_code))).join(
            BuyPlanLine, BuyPlanLine.sku_id == SKU.id
        ).where(BuyPlanLine.buy_plan_file_id == f.id)
    )
    total_styles = total_styles_row.scalar() or 0

    categories_rows = await db.execute(
        select(func.distinct(SKU.category)).join(
            BuyPlanLine, BuyPlanLine.sku_id == SKU.id
        ).where(BuyPlanLine.buy_plan_file_id == f.id).order_by(SKU.category)
    )
    categories = [r[0] for r in categories_rows.all() if r[0]]

    payload = {
        "id": str(f.id),
        "brand_id": str(f.brand_id),
        "season_id": str(f.season_id) if f.season_id else None,
        "name": f.name,
        "source_filename": f.source_filename,
        "notes": f.notes,
        "created_at": f.created_at.isoformat(),
        "updated_at": f.updated_at.isoformat(),
        "total_lines": int(total_lines),
        "total_units": int(total_units),
        "total_styles": int(total_styles),
        "categories": categories,
    }
    return envelope(payload)


@router.get("/{file_id}/lines")
async def get_buy_plan_lines(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    f = await db.get(BuyPlanFile, file_id)
    if f is None or f.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Buy plan not found"})

    # Join buy_plan_lines with skus to get SKU metadata
    stmt = (
        select(BuyPlanLine, SKU)
        .join(SKU, BuyPlanLine.sku_id == SKU.id)
        .where(BuyPlanLine.buy_plan_file_id == file_id)
        .order_by(SKU.style_code, SKU.size)
    )
    rows = (await db.execute(stmt)).all()

    lines = []
    for line, sku in rows:
        lines.append({
            "id": str(line.id),
            "buy_plan_file_id": str(line.buy_plan_file_id),
            "brand_id": str(line.brand_id),
            "sku_id": str(line.sku_id),
            "sku_code": sku.sku_code,
            "style_code": sku.style_code,
            "style_name": sku.style_name,
            "category": sku.category,
            "size": sku.size,
            "colour": sku.colour,
            "price_band": sku.price_band,
            "store_group_rule": line.store_group_rule,
            "style_risk_group": line.style_risk_group,
            "total_buy_qty": line.total_buy_qty,
            "expected_first_allocation_qty": line.expected_first_allocation_qty,
            "vendor_name": line.vendor_name,
            "expected_delivery_week": line.expected_delivery_week.isoformat() if line.expected_delivery_week else None,
            "planned_cost_per_unit": float(line.planned_cost_per_unit) if line.planned_cost_per_unit is not None else None,
            "moq": line.moq,
            "planned_price_per_unit": float(line.planned_price_per_unit) if line.planned_price_per_unit is not None else None,
            "planned_margin_pct": float(line.planned_margin_pct) if line.planned_margin_pct is not None else None,
            "created_at": line.created_at.isoformat(),
            "updated_at": line.updated_at.isoformat(),
        })

    return envelope(lines)


@router.patch("/{file_id}/lines/{line_id}")
async def update_buy_plan_line(
    file_id: UUID,
    line_id: UUID,
    payload: BuyPlanLineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    f = await db.get(BuyPlanFile, file_id)
    if f is None or f.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Buy plan not found"})

    line = await db.get(BuyPlanLine, line_id)
    if line is None or line.buy_plan_file_id != file_id or line.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Buy plan line not found"})

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(line, key, value)

    await db.commit()
    await db.refresh(line)

    # Return line with SKU data attached
    sku = await db.get(SKU, line.sku_id)
    result = {
        "id": str(line.id),
        "buy_plan_file_id": str(line.buy_plan_file_id),
        "brand_id": str(line.brand_id),
        "sku_id": str(line.sku_id),
        "sku_code": sku.sku_code if sku else None,
        "style_code": sku.style_code if sku else None,
        "style_name": sku.style_name if sku else None,
        "category": sku.category if sku else None,
        "size": sku.size if sku else None,
        "colour": sku.colour if sku else None,
        "price_band": sku.price_band if sku else None,
        "store_group_rule": line.store_group_rule,
        "style_risk_group": line.style_risk_group,
        "total_buy_qty": line.total_buy_qty,
        "expected_first_allocation_qty": line.expected_first_allocation_qty,
        "vendor_name": line.vendor_name,
        "expected_delivery_week": line.expected_delivery_week.isoformat() if line.expected_delivery_week else None,
        "planned_cost_per_unit": float(line.planned_cost_per_unit) if line.planned_cost_per_unit is not None else None,
        "moq": line.moq,
        "planned_price_per_unit": float(line.planned_price_per_unit) if line.planned_price_per_unit is not None else None,
        "planned_margin_pct": float(line.planned_margin_pct) if line.planned_margin_pct is not None else None,
        "created_at": line.created_at.isoformat(),
        "updated_at": line.updated_at.isoformat(),
    }
    return envelope(result)


@router.get("/{file_id}/reconcile")
async def reconcile_buy_plan(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    f = await db.get(BuyPlanFile, file_id)
    if f is None or f.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Buy plan not found"})

    if f.season_id is None:
        # No season linked — return empty reconciliation
        return envelope({
            "buy_plan_file_id": str(f.id),
            "season_id": None,
            "rows": [],
            "total_otb": 0.0,
            "total_committed": 0.0,
            "overall_usage_pct": 0.0,
        })

    # Pull all SeasonOTB rows for this season and brand
    otb_rows = (
        await db.execute(
            select(SeasonOTB).where(
                SeasonOTB.season_id == f.season_id,
                SeasonOTB.brand_id == current_user.brand_id,
            )
        )
    ).scalars().all()

    # Aggregate OTB by category: sum otb_value across all months
    otb_by_category: dict[str, float] = {}
    otb_planned_sales_by_category: dict[str, float] = {}
    otb_months_by_category: dict[str, list[str]] = {}

    for otb in otb_rows:
        cat = otb.category
        val = float(otb.otb_value) if otb.otb_value is not None else 0.0
        ps = float(otb.planned_sales) if otb.planned_sales is not None else 0.0
        month_str = otb.month.isoformat() if otb.month else ""

        otb_by_category[cat] = otb_by_category.get(cat, 0.0) + val
        otb_planned_sales_by_category[cat] = otb_planned_sales_by_category.get(cat, 0.0) + ps
        if cat not in otb_months_by_category:
            otb_months_by_category[cat] = []
        if month_str not in otb_months_by_category[cat]:
            otb_months_by_category[cat].append(month_str)

    # Pull all buy plan lines for this file, joined with SKUs for category
    lines_stmt = (
        select(BuyPlanLine, SKU.category)
        .join(SKU, BuyPlanLine.sku_id == SKU.id)
        .where(BuyPlanLine.buy_plan_file_id == file_id)
    )
    line_rows = (await db.execute(lines_stmt)).all()

    # Aggregate buy plan cost by category
    buy_cost_by_category: dict[str, float] = {}
    for line, category in line_rows:
        if not category:
            continue
        qty = line.total_buy_qty or 0
        cost = float(line.planned_cost_per_unit) if line.planned_cost_per_unit is not None else 0.0
        buy_cost_by_category[category] = buy_cost_by_category.get(category, 0.0) + (qty * cost)

    # Build reconciliation rows — one per category that appears in OTB
    all_categories = sorted(set(list(otb_by_category.keys()) + list(buy_cost_by_category.keys())))

    result_rows = []
    for cat in all_categories:
        otb_val = otb_by_category.get(cat, 0.0)
        planned_sales = otb_planned_sales_by_category.get(cat, 0.0)
        buy_cost = buy_cost_by_category.get(cat, 0.0)
        usage_pct = (buy_cost / otb_val * 100.0) if otb_val > 0 else 0.0
        is_overrun = usage_pct > 100.0

        # Use the first month for this category (for display grouping)
        months = otb_months_by_category.get(cat, [""])
        month_str = min(months) if months else ""

        result_rows.append({
            "category": cat,
            "month": month_str,
            "planned_sales": planned_sales,
            "otb_value": otb_val,
            "buy_plan_cost": buy_cost,
            "otb_usage_pct": round(usage_pct, 2),
            "is_overrun": is_overrun,
        })

    total_otb = sum(r["otb_value"] for r in result_rows)
    total_committed = sum(r["buy_plan_cost"] for r in result_rows)
    overall_usage_pct = (total_committed / total_otb * 100.0) if total_otb > 0 else 0.0

    return envelope({
        "buy_plan_file_id": str(f.id),
        "season_id": str(f.season_id),
        "rows": result_rows,
        "total_otb": round(total_otb, 2),
        "total_committed": round(total_committed, 2),
        "overall_usage_pct": round(overall_usage_pct, 2),
    })


@router.post("", status_code=201)
async def create_buy_plan(
    payload: BuyPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    await _validate_season_or_404(db, current_user.brand_id, payload.season_id)

    existing = await db.scalar(
        select(BuyPlanFile.id).where(
            BuyPlanFile.brand_id == current_user.brand_id,
            BuyPlanFile.name == payload.name,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT",
                "message": f"A buy plan named '{payload.name}' already exists for this brand",
            },
        )

    plan = BuyPlanFile(
        brand_id=current_user.brand_id,
        season_id=payload.season_id,
        name=payload.name,
        notes=payload.notes,
        source_filename=payload.source_filename,
        created_by=current_user.id,
    )
    db.add(plan)
    # First buy plan exits PLANNING.
    if payload.season_id is not None:
        await advance_season_if_earlier(
            db,
            brand_id=current_user.brand_id,
            season_id=payload.season_id,
            target=SeasonStatus.BUYING,
        )
    await db.commit()
    await db.refresh(plan)

    return envelope({
        **_serialize_plan(plan),
        "total_lines": 0,
        "total_units": 0,
        "total_styles": 0,
        "categories": [],
    })


@router.patch("/{file_id}")
async def update_buy_plan(
    file_id: UUID,
    payload: BuyPlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    plan = await _get_plan_or_404(db, current_user.brand_id, file_id)
    await _validate_season_or_404(db, current_user.brand_id, payload.season_id)

    if payload.name is not None and payload.name != plan.name:
        clash = await db.scalar(
            select(BuyPlanFile.id).where(
                BuyPlanFile.brand_id == current_user.brand_id,
                BuyPlanFile.name == payload.name,
                BuyPlanFile.id != plan.id,
            )
        )
        if clash is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONFLICT",
                    "message": f"A buy plan named '{payload.name}' already exists for this brand",
                },
            )

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, key, value)

    await db.commit()
    await db.refresh(plan)
    return envelope(_serialize_plan(plan))


@router.delete("/{file_id}", status_code=204)
async def delete_buy_plan(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> Response:
    plan = await _get_plan_or_404(db, current_user.brand_id, file_id)

    # Cascade-delete lines explicitly (no DB-level cascade defined)
    await db.execute(
        delete_stmt(BuyPlanLine).where(
            BuyPlanLine.buy_plan_file_id == plan.id,
            BuyPlanLine.brand_id == current_user.brand_id,
        )
    )
    await db.delete(plan)
    await db.commit()
    return Response(status_code=204)


@router.post("/{file_id}/lines", status_code=201)
async def create_buy_plan_line(
    file_id: UUID,
    payload: BuyPlanLineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    plan = await _get_plan_or_404(db, current_user.brand_id, file_id)
    sku = await _validate_sku_or_404(db, current_user.brand_id, payload.sku_id)

    # Enforce uniqueness on (file, sku, store_group_rule) at app level for clear 409
    existing = await db.scalar(
        select(BuyPlanLine.id).where(
            BuyPlanLine.buy_plan_file_id == plan.id,
            BuyPlanLine.sku_id == payload.sku_id,
            BuyPlanLine.store_group_rule == payload.store_group_rule,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT",
                "message": "A line for this SKU and store group already exists in this plan",
            },
        )

    line = BuyPlanLine(
        buy_plan_file_id=plan.id,
        brand_id=current_user.brand_id,
        sku_id=payload.sku_id,
        store_group_rule=payload.store_group_rule,
        style_risk_group=payload.style_risk_group,
        total_buy_qty=payload.total_buy_qty,
        expected_first_allocation_qty=payload.expected_first_allocation_qty,
        vendor_name=payload.vendor_name,
        expected_delivery_week=payload.expected_delivery_week,
        planned_cost_per_unit=payload.planned_cost_per_unit,
        moq=payload.moq,
        planned_price_per_unit=payload.planned_price_per_unit,
        planned_margin_pct=payload.planned_margin_pct,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)

    return envelope(_serialize_line(line, sku))


@router.delete("/{file_id}/lines/{line_id}", status_code=204)
async def delete_buy_plan_line(
    file_id: UUID,
    line_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> Response:
    plan = await _get_plan_or_404(db, current_user.brand_id, file_id)
    line = await db.get(BuyPlanLine, line_id)
    if (
        line is None
        or line.buy_plan_file_id != plan.id
        or line.brand_id != current_user.brand_id
    ):
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Buy plan line not found"},
        )

    await db.delete(line)
    await db.commit()
    return Response(status_code=204)
