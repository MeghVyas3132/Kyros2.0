from datetime import datetime
from uuid import UUID

import logging
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import (
    AllocationLine,
    AllocationSession,
    AllocationStatus,
    BuyPlanFile,
    GRN,
    GRNLine,
    GRNLineReservation,
    InventoryReservationType,
    SKU,
    SalesData,
    Store,
    StoreProductGrade,
    User,
    UserRole,
)
from app.routers._helpers import envelope
from app.schemas.allocation import (
    AllocationGenerateRequest,
    AllocationLineUpdate,
    AllocationSimulateRequest,
)
from app.services.allocation.benchmark import BenchmarkLine, build_benchmark_report
from app.services.allocation.engine import AllocationEngine
from app.services.allocation.explainer import generate_human_reasoning, normalize_projections, normalize_reasoning
from app.services.allocation.simulator import simulate_quantity
from app.services.allocation.story_concentration import compute_story_concentration
from app.services.llm.narration import narrate_allocation_line, narrate_sanity_check
from app.services.workflow_state import advance_season_if_earlier
from app.models import SeasonStatus
from app.utils.date_utils import utcnow

router = APIRouter(prefix="/api/v1/allocation", tags=["allocation"])
engine = AllocationEngine()
logger = logging.getLogger(__name__)


# ── Track A: pre-allocation data sanity ──────────────────────────────────────


@router.get("/sanity-check")
async def sanity_check(
    grn_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pre-flight check before generating an allocation.

    Returns:
      - blockers: hard issues that should stop allocation outright
      - warnings: amber issues the planner can acknowledge and proceed
      - facts: raw counts for the UI to render badges
      - narration: LLM-generated 1-2 sentence summary (template fallback)
    """
    grn = await db.get(GRN, grn_id)
    if grn is None or grn.brand_id != current_user.brand_id:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "GRN not found"}
        )

    # Sales history depth (in weeks) anywhere in the brand
    weeks_of_sales = await db.scalar(
        select(func.count(func.distinct(SalesData.week_start_date))).where(
            SalesData.brand_id == current_user.brand_id
        )
    ) or 0

    # GRN SKUs and how many of them have a sales row (any time)
    grn_sku_rows = (
        await db.execute(
            select(GRNLine.sku_id).where(GRNLine.grn_id == grn.id)
        )
    ).all()
    grn_sku_ids = [r[0] for r in grn_sku_rows]

    grn_skus_with_history = 0
    if grn_sku_ids:
        grn_skus_with_history = await db.scalar(
            select(func.count(func.distinct(SalesData.sku_id))).where(
                SalesData.brand_id == current_user.brand_id,
                SalesData.sku_id.in_(grn_sku_ids),
            )
        ) or 0

    # GRN's distinct categories from SKU master
    grn_categories: list[str] = []
    if grn_sku_ids:
        cat_rows = (
            await db.execute(
                select(func.distinct(SKU.category))
                .where(
                    SKU.brand_id == current_user.brand_id,
                    SKU.id.in_(grn_sku_ids),
                    SKU.category.is_not(None),
                )
            )
        ).all()
        grn_categories = sorted({c[0] for c in cat_rows if c[0]})

    # Active stores in brand
    active_stores = await db.scalar(
        select(func.count(Store.id)).where(
            Store.brand_id == current_user.brand_id,
            Store.is_active.is_(True),
        )
    ) or 0

    # Stores graded for *all* GRN categories
    stores_with_grades_for_grn_categories = 0
    if grn_categories and active_stores:
        graded = await db.scalar(
            select(func.count(func.distinct(StoreProductGrade.store_id))).where(
                StoreProductGrade.brand_id == current_user.brand_id,
                StoreProductGrade.product_category.in_(grn_categories),
            )
        ) or 0
        stores_with_grades_for_grn_categories = int(graded)

    # Buy plan for the season (if season known)
    buy_plan_count = 0
    if grn.season_id is not None:
        buy_plan_count = await db.scalar(
            select(func.count(BuyPlanFile.id)).where(
                BuyPlanFile.brand_id == current_user.brand_id,
                BuyPlanFile.season_id == grn.season_id,
            )
        ) or 0

    # ── Decisions ────────────────────────────────────────────────────────────

    blockers: list[str] = []
    warnings: list[str] = []

    if int(weeks_of_sales) == 0:
        blockers.append(
            "No sales history loaded for this brand — allocation cannot project demand."
        )
    elif int(weeks_of_sales) < 8:
        warnings.append(
            f"Only {int(weeks_of_sales)} week(s) of sales history — recommendations will rely on grade-average and analogue fallbacks."
        )

    if grn_sku_ids and int(grn_skus_with_history) / len(grn_sku_ids) < 0.5:
        warnings.append(
            f"{len(grn_sku_ids) - int(grn_skus_with_history)} of {len(grn_sku_ids)} GRN SKUs have no sales history — those will use style-DNA analogues."
        )

    if active_stores == 0:
        blockers.append("No active stores in this brand — nothing to allocate to.")

    if (
        grn_categories
        and active_stores
        and stores_with_grades_for_grn_categories / int(active_stores) < 0.5
    ):
        warnings.append(
            f"Only {stores_with_grades_for_grn_categories} of {int(active_stores)} stores have grades for the GRN categories — most stores will fall back to default 'C'."
        )

    if grn.season_id is not None and buy_plan_count == 0:
        warnings.append(
            "No buy plan linked to this season — allocation will run but you lose OTB reconciliation context."
        )

    facts = {
        "weeks_of_sales": int(weeks_of_sales),
        "grn_sku_count": len(grn_sku_ids),
        "grn_skus_with_history": int(grn_skus_with_history),
        "grn_categories": grn_categories,
        "active_stores": int(active_stores),
        "stores_with_grades_for_grn_categories": int(stores_with_grades_for_grn_categories),
        "buy_plan_count": int(buy_plan_count),
        "blockers": blockers,
        "warnings": warnings,
    }
    narration = await narrate_sanity_check(facts)

    return envelope(
        {
            "grn_id": str(grn.id),
            "ready": len(blockers) == 0,
            "blockers": blockers,
            "warnings": warnings,
            "facts": facts,
            "narration": narration,
        }
    )


async def _load_session_lines(
    session_id: UUID,
    brand_id: UUID,
    db: AsyncSession,
    *,
    line_limit: int | None = None,
    line_offset: int = 0,
) -> list[dict]:
    session = await db.get(AllocationSession, session_id)
    if session is None:
        return []

    grn_line_rows = (
        await db.execute(
            select(GRNLine).where(
                GRNLine.grn_id == session.grn_id,
                GRNLine.brand_id == brand_id,
            )
        )
    ).scalars().all()
    grn_line_by_sku = {line.sku_id: line for line in grn_line_rows}
    grn_line_ids = [line.id for line in grn_line_rows]

    reservation_by_line: dict[UUID, list[dict]] = {line_id: [] for line_id in grn_line_ids}
    if grn_line_ids:
        reservation_rows = await db.execute(
            select(GRNLineReservation, InventoryReservationType)
            .join(
                InventoryReservationType,
                InventoryReservationType.id == GRNLineReservation.reservation_type_id,
            )
            .where(
                GRNLineReservation.grn_line_id.in_(grn_line_ids),
                GRNLineReservation.brand_id == brand_id,
                InventoryReservationType.brand_id == brand_id,
            )
            .order_by(InventoryReservationType.display_order.asc(), InventoryReservationType.code.asc())
        )
        for reservation, reservation_type in reservation_rows.all():
            reservation_by_line[reservation.grn_line_id].append(
                {
                    "code": reservation_type.code,
                    "label": reservation_type.label,
                    "reserved_qty": reservation.reserved_qty,
                    "deducts_from_first_allocation": reservation_type.deducts_from_first_allocation,
                    "is_active": reservation_type.is_active,
                }
            )

    line_query = (
        select(AllocationLine, Store, SKU)
        .join(Store, Store.id == AllocationLine.store_id)
        .join(SKU, SKU.id == AllocationLine.sku_id)
        .where(
            AllocationLine.session_id == session_id,
            AllocationLine.brand_id == brand_id,
            Store.brand_id == brand_id,
            SKU.brand_id == brand_id,
        )
        .order_by(Store.store_name.asc(), SKU.style_name.asc(), SKU.size.asc())
        .offset(max(0, int(line_offset)))
    )
    if line_limit is not None:
        line_query = line_query.limit(int(line_limit))

    rows = await db.execute(line_query)
    records: list[dict] = []
    for line, store, sku in rows.all():
        grn_line = grn_line_by_sku.get(sku.id)
        reservation_rows = reservation_by_line.get(grn_line.id, []) if grn_line else []
        if grn_line:
            if reservation_rows:
                reserved_for_allocation = sum(
                    int(item["reserved_qty"] or 0)
                    for item in reservation_rows
                    if item.get("deducts_from_first_allocation") and item.get("is_active")
                )
            else:
                reserved_for_allocation = int(grn_line.ecom_reserved_qty or 0) + int(grn_line.ars_reserved_qty or 0)
            available_for_first_allocation = max(0, int(grn_line.units_received or 0) - reserved_for_allocation)
        else:
            available_for_first_allocation = None

        _normalized_reasoning = normalize_reasoning(line.ai_reasoning)
        payload = {
            "id": line.id,
            "session_id": line.session_id,
            "brand_id": line.brand_id,
            "store_id": line.store_id,
            "sku_id": line.sku_id,
            "ai_recommended_qty": line.ai_recommended_qty,
            "ai_confidence": line.ai_confidence,
            "ai_reasoning": _normalized_reasoning,
            "ai_reasoning_human": generate_human_reasoning(_normalized_reasoning),
            "ai_projections": normalize_projections(line.ai_projections),
            "final_qty": line.final_qty,
            "was_overridden": line.was_overridden,
            "override_reason": line.override_reason,
            "override_reason_code": line.override_reason_code,
            "override_notes": line.override_notes,
            "store_code": store.store_code,
            "store_name": store.store_name,
            "store_city": store.city,
            "sku_code": sku.sku_code,
            "style_name": sku.style_name,
            "sku_size": sku.size,
            "sku_category": sku.category,
            "sku_fabric": sku.fabric,
            "sku_colour": sku.colour,
            "sku_price_band": sku.price_band,
            "sku_store_group_rule": sku.store_group_rule,
            "sku_resolved_min_grade": sku.resolved_min_grade,
            "sku_style_risk_group": sku.style_risk_group,
            "sku_resolved_risk_level": sku.resolved_risk_level,
            "sku_story": sku.story,
            "sku_sub_story": sku.sub_story,
            "grn_units_received": grn_line.units_received if grn_line else None,
            "grn_total_buy_qty": grn_line.total_buy_qty if grn_line else None,
            "grn_ecom_reserved_qty": grn_line.ecom_reserved_qty if grn_line else None,
            "grn_ars_reserved_qty": grn_line.ars_reserved_qty if grn_line else None,
            "grn_available_for_first_allocation": available_for_first_allocation,
            "grn_reservations": reservation_rows,
            "created_at": line.created_at,
            "updated_at": line.updated_at,
        }
        records.append(payload)
    return records


@router.post("/generate")
async def generate_allocation(
    payload: AllocationGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    grn = await db.get(GRN, payload.grn_id)
    if grn is None or grn.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "GRN not found"})

    # Check for existing session
    existing = await db.scalar(
        select(AllocationSession).where(
            AllocationSession.grn_id == payload.grn_id,
            AllocationSession.brand_id == current_user.brand_id,
        )
    )
    if existing is not None:
        if existing.status == AllocationStatus.GENERATING:
            return envelope(existing)  # already running
        if existing.status == AllocationStatus.APPROVED:
            return envelope(existing)  # already approved
        if existing.status == AllocationStatus.UNDER_REVIEW:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONFLICT",
                    "message": (
                        "This allocation is currently under review. Regenerating will discard "
                        "review progress. Reset the session to DRAFT before regenerating."
                    ),
                },
            )

    # Create/reuse session with GENERATING status
    if existing is None:
        session = AllocationSession(
            brand_id=current_user.brand_id,
            grn_id=payload.grn_id,
            season_id=grn.season_id,
            status=AllocationStatus.GENERATING,
            failure_reason=None,
            generated_at=utcnow(),
            total_stores=0,
        )
        db.add(session)
    else:
        session = existing
        session.status = AllocationStatus.GENERATING
        session.failure_reason = None
        session.generated_at = utcnow()
    await db.commit()
    await db.refresh(session)

    # Dispatch to Celery worker
    from app.tasks.allocation import run_allocation_task
    try:
        run_allocation_task.apply_async(
            args=[str(session.id), str(payload.grn_id), str(current_user.brand_id)],
        )
    except Exception as e:
        logger.error(f"Celery dispatch failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=(
                "Allocation queue is unavailable. "
                "Please try again in a few seconds."
            ),
        )

    return envelope(session)


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = (
        await db.execute(
            select(AllocationSession, GRN)
            .outerjoin(GRN, GRN.id == AllocationSession.grn_id)
            .where(AllocationSession.brand_id == current_user.brand_id)
            .order_by(desc(AllocationSession.generated_at), desc(AllocationSession.created_at))
        )
    ).all()

    result = []
    for session, grn in rows:
        session_payload = jsonable_encoder(session)
        session_payload["grn"] = (
            {
                "grn_code": grn.grn_code,
                "total_units": grn.total_units,
                "total_skus": grn.total_skus,
            }
            if grn is not None
            else None
        )
        result.append(session_payload)

    return envelope(result)


@router.get("/sessions/by-grn/{grn_id}")
async def get_session_by_grn(
    grn_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    session = await db.scalar(
        select(AllocationSession)
        .where(
            AllocationSession.grn_id == grn_id,
            AllocationSession.brand_id == current_user.brand_id,
        )
        .order_by(AllocationSession.created_at.desc())
    )
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Session not found"})
    return envelope(session)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    line_limit: int | None = Query(default=None, ge=1, le=20000),
    line_offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    session = await db.get(AllocationSession, session_id)
    if session is None or session.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Session not found"})

    lines = await _load_session_lines(
        session_id,
        current_user.brand_id,
        db,
        line_limit=line_limit,
        line_offset=line_offset,
    )

    payload: dict = {"session": session, "lines": lines}
    if line_limit is not None:
        total_lines = await db.scalar(
            select(func.count(AllocationLine.id)).where(
                AllocationLine.session_id == session_id,
                AllocationLine.brand_id == current_user.brand_id,
            )
        )
        total = int(total_lines or 0)
        payload.update(
            {
                "lines_total": total,
                "lines_returned": len(lines),
                "lines_offset": line_offset,
                "lines_has_more": (line_offset + len(lines)) < total,
            }
        )

    return envelope(payload)


@router.post("/sessions/{session_id}/recover")
async def recover_stuck_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
):
    session = await db.get(AllocationSession, session_id)
    if session is None or session.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Session not found"})

    if session.status != AllocationStatus.GENERATING:
        raise HTTPException(
            status_code=400,
            detail=f"Session is {session.status}, not GENERATING.",
        )

    # Only recover if session has been stuck for >45 minutes.
    stuck_since = session.updated_at or session.created_at
    if (datetime.utcnow() - stuck_since).total_seconds() < 2700:
        raise HTTPException(
            status_code=400,
            detail=(
                "Session has been GENERATING for less than 45 minutes. "
                "Wait before recovering."
            ),
        )

    session.status = AllocationStatus.FAILED
    session.failure_reason = (
        "Recovered from stuck GENERATING state. "
        "Worker likely crashed. Please regenerate."
    )
    await db.commit()
    return {"status": "recovered", "session_id": str(session_id)}


@router.put("/lines/{line_id}")
async def update_line(
    line_id: UUID,
    payload: AllocationLineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    line = await db.get(AllocationLine, line_id)
    if line is None or line.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Line not found"})

    override_qty = int(payload.final_qty)

    # Get the GRN line for this allocation line.
    grn_line = await db.execute(
        select(GRNLine)
        .join(AllocationSession, AllocationSession.grn_id == GRNLine.grn_id)
        .join(AllocationLine, AllocationLine.session_id == AllocationSession.id)
        .where(AllocationLine.id == line_id)
    )
    grn_line = grn_line.scalar_one_or_none()

    if grn_line:
        # Sum all other final_qty for same SKU in this session.
        other_lines_total = await db.scalar(
            select(func.sum(AllocationLine.final_qty))
            .where(
                AllocationLine.session_id == line.session_id,
                AllocationLine.sku_id == line.sku_id,
                AllocationLine.id != line_id,
            )
        ) or 0

        available = (
            int(grn_line.units_received or 0)
            - int(grn_line.ecom_reserved_qty or 0)
            - int(grn_line.ars_reserved_qty or 0)
        )

        if int(other_lines_total) + override_qty > available:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Override quantity {override_qty} would exceed "
                    f"available inventory. "
                    f"Available: {available}, "
                    f"Already allocated to other stores: "
                    f"{int(other_lines_total)}"
                ),
            )

    # Capture the engine's prior value BEFORE overwriting — otherwise the
    # comparison below is always against the new value.
    # ai_recommended_qty is the raw demand before capping; final_qty is what the
    # engine actually set after inventory cap / constraints.
    original_engine_qty = (
        line.final_qty if line.final_qty is not None else line.ai_recommended_qty
    )
    line.final_qty = payload.final_qty
    line.override_reason = payload.override_reason
    line.override_reason_code = payload.override_reason_code
    line.override_notes = payload.override_notes
    line.was_overridden = int(payload.final_qty) != int(original_engine_qty)

    await db.commit()
    await db.refresh(line)
    return envelope(line)


@router.get("/lines/{line_id}/narration")
async def get_line_narration(
    line_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """LLM-narrated 2-3 sentence explanation for one allocation line.

    Cached process-side. Falls back to the deterministic template
    transparently if the LLM is disabled or every Groq key fails."""
    line = await db.get(AllocationLine, line_id)
    if line is None or line.brand_id != current_user.brand_id:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "Line not found"}
        )

    normalized = normalize_reasoning(line.ai_reasoning)
    text = await narrate_allocation_line(normalized)
    return envelope(
        {
            "line_id": str(line.id),
            "narration": text,
            "fallback": generate_human_reasoning(normalized),
        }
    )


@router.post("/simulate")
async def simulate(
    payload: AllocationSimulateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await simulate_quantity(
        current_user.brand_id,
        payload.store_id,
        payload.sku_id,
        payload.quantity,
        db,
    )
    return envelope(result)


@router.post("/sessions/{session_id}/approve")
async def approve_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    session = await db.get(AllocationSession, session_id)
    if session is None or session.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Session not found"})

    lines = (
        await db.execute(
            select(AllocationLine).where(
                AllocationLine.session_id == session_id,
                AllocationLine.brand_id == current_user.brand_id,
            )
        )
    ).scalars().all()

    approved_units = 0
    for line in lines:
        if line.final_qty is None:
            line.final_qty = line.ai_recommended_qty
        line.was_overridden = line.final_qty != line.ai_recommended_qty
        approved_units += line.final_qty or 0

    session.status = AllocationStatus.APPROVED
    session.approved_by = current_user.id
    session.approved_at = utcnow()
    session.total_units_approved = approved_units

    grn = await db.get(GRN, session.grn_id)
    if grn is not None:
        grn.status = "ALLOCATED"

    # Approving the allocation means inventory is committed → IN_SEASON.
    if session.season_id is not None:
        await advance_season_if_earlier(
            db,
            brand_id=current_user.brand_id,
            season_id=session.season_id,
            target=SeasonStatus.IN_SEASON,
        )

    await db.commit()
    await db.refresh(session)
    return envelope(session)


from fastapi.responses import StreamingResponse
import csv
import io

async def _csv_row_generator(session_id: UUID, brand_id: UUID, db: AsyncSession, include_zero: bool):
    yield "GRN Code,SKU Code,Style Name,Size,Store Code,Store Name,City,Quantity\n"
    
    offset = 0
    batch_size = 5000
    grn_code = ""
    session = await db.get(AllocationSession, session_id)
    if session and session.grn_id:
        grn = await db.get(GRN, session.grn_id)
        if grn:
            grn_code = grn.grn_code or ""

    while True:
        lines = await _load_session_lines(session_id, brand_id, db, line_limit=batch_size, line_offset=offset)
        if not lines:
            break
            
        for line in lines:
            qty = (
                line.get("final_qty")
                if line.get("final_qty") is not None
                else line.get("ai_recommended_qty", 0)
            )
            if not include_zero and int(qty or 0) <= 0:
                continue
                
            # Using basic CSV formatting, escape strings with commas
            row = [
                grn_code,
                line.get("sku_code", ""),
                str(line.get("style_name", "")),
                line.get("sku_size", ""),
                line.get("store_code", ""),
                str(line.get("store_name", "")),
                str(line.get("store_city", "")),
                str(qty)
            ]
            
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(row)
            yield output.getvalue()
            
        offset += batch_size

@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: UUID,
    include_zero: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(AllocationSession, session_id)
    if session is None or session.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Session not found"})

    return StreamingResponse(
        _csv_row_generator(session_id, current_user.brand_id, db, include_zero),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=allocation-{session_id}.csv"},
    )


@router.get("/{allocation_id}/insights")
async def get_allocation_insights(
    allocation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return VP-level insight cards for an allocation session."""
    
    session = await db.get(AllocationSession, allocation_id)
    if session is None or session.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Fetch all allocation lines with demand data
    result = await db.execute(
        select(AllocationLine)
        .where(AllocationLine.session_id == allocation_id)
        .where(AllocationLine.final_qty > 0)
    )
    lines = result.scalars().all()
    
    if not lines:
        return envelope({
            "lost_sales_correction": {
                "stores_corrected": 0,
                "estimated_recovered_units": 0,
                "headline": "No allocation lines found for this session.",
                "subtext": "",
            },
            "under_covered_stores": {"count": 0, "headline": ""},
            "confidence_breakdown": {"high": 0, "moderate": 0, "low": 0},
            "total_lines": 0,
            "total_units_allocated": 0,
        })
    
    # Calculate metrics from reasoning payload
    corrected_lines = [
        l for l in lines 
        if isinstance(l.ai_reasoning, dict) and l.ai_reasoning.get("is_stockout_corrected")
    ]
    
    under_covered = [
        l for l in lines
        if isinstance(l.ai_reasoning, dict) and (
            l.ai_reasoning.get("weeks_cover_at_recommended", 99) < 
            l.ai_reasoning.get("cover_target_weeks", 0) * 0.7
        )
    ]
    
    def confidence_tier(line):
        basis = line.ai_reasoning.get("confidence_basis", "") if isinstance(line.ai_reasoning, dict) else ""
        if "High" in basis:
            return "high"
        if "Moderate" in basis:
            return "moderate"
        return "low"
    
    demand_breakdown = {
        "store_historical": sum(1 for l in lines if isinstance(l.ai_reasoning, dict) and l.ai_reasoning.get("ros_source") == "store_historical"),
        "cluster_average": sum(1 for l in lines if isinstance(l.ai_reasoning, dict) and l.ai_reasoning.get("ros_source") == "cluster_average"),
        "grade_average": sum(1 for l in lines if isinstance(l.ai_reasoning, dict) and l.ai_reasoning.get("ros_source") == "grade_average"),
        "style_dna": sum(1 for l in lines if isinstance(l.ai_reasoning, dict) and l.ai_reasoning.get("ros_source") == "style_dna"),
        "minimum_presentation": sum(1 for l in lines if isinstance(l.ai_reasoning, dict) and l.ai_reasoning.get("ros_source") == "minimum_presentation"),
    }
    total_allocated = sum(l.final_qty for l in lines if l.final_qty)
    utilization_pct = round(total_allocated / max(session.total_units_recommended, 1) * 100, 1)

    return envelope({
        "session_health": {
            "utilization_pct": utilization_pct,
            "stores_receiving_allocation": len(set(l.store_id for l in lines if l.final_qty and l.final_qty > 0)),
            "stores_at_minimum": sum(1 for l in lines if isinstance(l.ai_reasoning, dict) and l.ai_reasoning.get("risk_flags", {}).get("heavy_cap_applied")),
            "stores_defaulted_to_grade_c": sum(1 for l in lines if isinstance(l.ai_reasoning, dict) and l.ai_reasoning.get("risk_flags", {}).get("grade_defaulted")),
            "demand_source_breakdown": demand_breakdown,
        },
        "lost_sales_correction": {
            "stores_corrected": len(set(l.store_id for l in corrected_lines)),
            "estimated_recovered_units": round(sum(
                (l.ai_reasoning.get("lost_sales_estimate") or 0) if isinstance(l.ai_reasoning, dict) else 0
                for l in corrected_lines
            )),
            "headline": f"Stockout correction applied to {len(set(l.store_id for l in corrected_lines))} stores.",
            "subtext": "These stores stocked out in SS25. Allocations corrected upward.",
        },
        "under_covered_stores": {
            "count": len(set(l.store_id for l in under_covered)),
            "headline": (
                f"{len(set(l.store_id for l in under_covered))} stores below target cover "
                f"due to inventory constraints."
            ),
        },
        "confidence_breakdown": {
            "high": sum(1 for l in lines if confidence_tier(l) == "high"),
            "moderate": sum(1 for l in lines if confidence_tier(l) == "moderate"),
            "low": sum(1 for l in lines if confidence_tier(l) == "low"),
        },
        "total_lines": len(lines),
        "total_units_allocated": total_allocated,
    })


@router.get("/sessions/{session_id}/benchmark")
async def get_session_benchmark(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(AllocationSession, session_id)
    if session is None or session.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Session not found"})

    line_rows = await db.execute(
        select(AllocationLine, SKU)
        .join(SKU, SKU.id == AllocationLine.sku_id)
        .where(
            AllocationLine.session_id == session_id,
            AllocationLine.brand_id == current_user.brand_id,
            SKU.brand_id == current_user.brand_id,
        )
    )

    grn_lines = (
        await db.execute(
            select(GRNLine).where(
                GRNLine.grn_id == session.grn_id,
                GRNLine.brand_id == current_user.brand_id,
            )
        )
    ).scalars().all()
    grn_line_ids = [line.id for line in grn_lines]

    reservation_map: dict[UUID, int] = {}
    if grn_line_ids:
        reservation_rows = await db.execute(
            select(
                GRNLineReservation.grn_line_id,
                func.coalesce(func.sum(GRNLineReservation.reserved_qty), 0).label("reserved_sum"),
            )
            .join(
                InventoryReservationType,
                and_(
                    InventoryReservationType.id == GRNLineReservation.reservation_type_id,
                    InventoryReservationType.brand_id == current_user.brand_id,
                    InventoryReservationType.is_active.is_(True),
                    InventoryReservationType.deducts_from_first_allocation.is_(True),
                ),
            )
            .where(
                GRNLineReservation.grn_line_id.in_(grn_line_ids),
                GRNLineReservation.brand_id == current_user.brand_id,
            )
            .group_by(GRNLineReservation.grn_line_id)
        )
        reservation_map = {row.grn_line_id: int(row.reserved_sum or 0) for row in reservation_rows.all()}

    available_units_total = 0
    for grn_line in grn_lines:
        reserved = reservation_map.get(grn_line.id)
        if reserved is None:
            reserved = int(grn_line.ecom_reserved_qty or 0) + int(grn_line.ars_reserved_qty or 0)
        available_units_total += max(0, int(grn_line.units_received or 0) - reserved)

    def _safe_float(value: object | None) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    benchmark_lines: list[BenchmarkLine] = []
    for line, sku in line_rows.all():
        reasoning = normalize_reasoning(line.ai_reasoning)
        resolved_final_qty = int(
            line.final_qty if line.final_qty is not None else (line.ai_recommended_qty or 0)
        )

        benchmark_lines.append(
            BenchmarkLine(
                final_qty=resolved_final_qty,
                ai_recommended_qty=int(line.ai_recommended_qty or 0),
                was_overridden=bool(line.was_overridden),
                ai_confidence=(line.ai_confidence or None),
                ros_source=(reasoning.get("ros_source") if isinstance(reasoning, dict) else None),
                cover_target_weeks=(
                    _safe_float(reasoning.get("cover_target_weeks"))
                    if isinstance(reasoning, dict)
                    else None
                ),
                weeks_cover_at_recommended=(
                    _safe_float(reasoning.get("weeks_cover_at_recommended"))
                    if isinstance(reasoning, dict)
                    else None
                ),
                store_grade=(
                    str(
                        (reasoning.get("store_grade") or reasoning.get("grade") or "")
                        if isinstance(reasoning, dict)
                        else ""
                    )
                    or None
                ),
                required_min_grade=sku.resolved_min_grade,
                style_risk_group=sku.style_risk_group,
            )
        )

    # Fetch season context for context-aware thresholds
    from app.services.allocation.health import AllocationHealthAnalyzer
    analyzer = AllocationHealthAnalyzer(session_id, current_user.brand_id, db)
    season_context = await analyzer.get_context()

    report = build_benchmark_report(
        lines=benchmark_lines,
        available_units_total=available_units_total,
        season_context=season_context,
    )
    report.update(
        {
            "session_id": str(session.id),
            "session_status": session.status.value if isinstance(session.status, AllocationStatus) else str(session.status),
        }
    )
    return envelope(report)


@router.get("/sessions/{session_id}/stores/{store_id}/story-concentration")
async def get_story_concentration(
    session_id: UUID,
    store_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    session = await db.get(AllocationSession, session_id)
    if session is None or session.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Session not found"})

    payload = await compute_story_concentration(
        session_id=session_id,
        store_id=store_id,
        brand_id=current_user.brand_id,
        db=db,
    )
    return envelope(payload)


@router.get("/sessions/{session_id}/decision-summary")
async def get_decision_summary(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Portfolio-level decision pack for a finished allocation.

    Returns a 3-5 action recommendation list plus a one-paragraph summary
    and a DATA / STRATEGY / HEALTHY classification. The endpoint is
    read-only and can be hit any number of times — the actions are
    re-derived from the stored ``health_report`` + a single per-style
    aggregation each call. Cheap. Idempotent.

    409 when the session has no ``health_report`` yet (intelligence layer
    hasn't run, e.g. session is still GENERATING).
    """
    from app.services.decision import build_decision_summary

    try:
        summary = await build_decision_summary(
            session_id=session_id,
            brand_id=current_user.brand_id,
            db=db,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": message},
            ) from exc
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": message},
        ) from exc

    return envelope(summary.to_dict())
