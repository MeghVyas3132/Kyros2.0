from datetime import datetime
from uuid import UUID

import logging
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import (
    AllocationLine,
    AllocationSession,
    AllocationStatus,
    GRN,
    GRNLine,
    GRNLineReservation,
    InventoryReservationType,
    SKU,
    Store,
    User,
    UserRole,
)
from app.routers._helpers import envelope
from app.schemas.allocation import (
    AllocationGenerateRequest,
    AllocationLineUpdate,
    AllocationSimulateRequest,
)
from app.services.allocation.engine import AllocationEngine
from app.services.allocation.explainer import normalize_projections, normalize_reasoning
from app.services.allocation.simulator import simulate_quantity
from app.services.allocation.story_concentration import compute_story_concentration
from app.utils.date_utils import utcnow

router = APIRouter(prefix="/api/v1/allocation", tags=["allocation"])
engine = AllocationEngine()
logger = logging.getLogger(__name__)


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

        payload = {
            "id": line.id,
            "session_id": line.session_id,
            "brand_id": line.brand_id,
            "store_id": line.store_id,
            "sku_id": line.sku_id,
            "ai_recommended_qty": line.ai_recommended_qty,
            "ai_confidence": line.ai_confidence,
            "ai_reasoning": normalize_reasoning(line.ai_reasoning),
            "ai_projections": normalize_projections(line.ai_projections),
            "final_qty": line.final_qty,
            "was_overridden": line.was_overridden,
            "override_reason": line.override_reason,
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

    # Only recover if session has been stuck for >30 minutes.
    stuck_since = session.updated_at or session.created_at
    if (datetime.utcnow() - stuck_since).total_seconds() < 1800:
        raise HTTPException(
            status_code=400,
            detail=(
                "Session has been GENERATING for less than 30 minutes. "
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

    line.final_qty = payload.final_qty
    line.override_reason = payload.override_reason
    line.override_notes = payload.override_notes
    line.was_overridden = payload.final_qty != line.ai_recommended_qty

    await db.commit()
    await db.refresh(line)
    return envelope(line)


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

    await db.commit()
    await db.refresh(session)
    return envelope(session)


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

    lines = await _load_session_lines(session_id, current_user.brand_id, db)

    records = []
    grn = await db.get(GRN, session.grn_id)
    for line in lines:
        qty = (
            line.get("final_qty")
            if line.get("final_qty") is not None
            else line.get("ai_recommended_qty", 0)
        )
        if not include_zero and int(qty or 0) <= 0:
            continue

        records.append(
            {
                "GRN Code": grn.grn_code if grn else "",
                "SKU Code": line.get("sku_code", ""),
                "Style Name": line.get("style_name", ""),
                "Size": line.get("sku_size", ""),
                "Store Code": line.get("store_code", ""),
                "Store Name": line.get("store_name", ""),
                "City": line.get("store_city", ""),
                "Quantity": qty,
            }
        )

    df = pd.DataFrame(records)
    csv_data = df.to_csv(index=False)
    return Response(
        content=csv_data,
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
    
    return envelope({
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
        "total_units_allocated": sum(l.final_qty for l in lines if l.final_qty),
    })


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
