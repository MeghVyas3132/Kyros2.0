from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
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
from app.services.allocation.simulator import simulate_quantity
from app.services.allocation.story_concentration import compute_story_concentration
from app.utils.date_utils import utcnow

router = APIRouter(prefix="/api/v1/allocation", tags=["allocation"])
engine = AllocationEngine()


async def _load_session_lines(
    session_id: UUID, brand_id: UUID, db: AsyncSession
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

    rows = await db.execute(
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
    )
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
            "ai_reasoning": line.ai_reasoning,
            "ai_projections": line.ai_projections,
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

    # Create/reuse session with GENERATING status
    if existing is None:
        session = AllocationSession(
            brand_id=current_user.brand_id,
            grn_id=payload.grn_id,
            season_id=grn.season_id,
            status=AllocationStatus.GENERATING,
            generated_at=utcnow(),
            total_stores=0,
        )
        db.add(session)
    else:
        session = existing
        session.status = AllocationStatus.GENERATING
        session.generated_at = utcnow()
    await db.commit()
    await db.refresh(session)

    # Dispatch to Celery worker
    from app.tasks.allocation import run_allocation_task
    try:
        run_allocation_task.apply_async(
            args=[str(session.id), str(payload.grn_id), str(current_user.brand_id)],
        )
    except Exception:
        # Celery unavailable — fall back to synchronous (blocks, but works)
        import logging
        logging.getLogger(__name__).warning("Celery unavailable, running allocation synchronously")
        await engine.generate(payload.grn_id, current_user.brand_id, db)
        await db.commit()
        await db.refresh(session)

    return envelope(session)


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List all allocation sessions for the current brand"""
    from sqlalchemy import desc
    
    sessions = (
        await db.execute(
            select(AllocationSession)
            .where(AllocationSession.brand_id == current_user.brand_id)
            .order_by(desc(AllocationSession.generated_at), desc(AllocationSession.created_at))
        )
    ).scalars().all()
    
    # Enrich sessions with GRN data
    result = []
    for session in sessions:
        try:
            grn = await db.get(GRN, session.grn_id)
            session_data = {
                "id": str(session.id),
                "grn_id": str(session.grn_id),
                "brand_id": str(session.brand_id),
                "season_id": str(session.season_id) if session.season_id else None,
                "status": session.status.value if session.status else None,
                "total_stores": session.total_stores,
                "generated_at": session.generated_at.isoformat() if session.generated_at else None,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "grn": {
                    "grn_code": grn.grn_code,
                    "total_units": grn.total_units,
                    "total_skus": grn.total_skus,
                } if grn else None,
            }
            result.append(session_data)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to enrich session {session.id}: {str(e)}")
            # Still include the session even if GRN enrichment fails
            session_data = {
                "id": str(session.id),
                "grn_id": str(session.grn_id),
                "brand_id": str(session.brand_id),
                "season_id": str(session.season_id) if session.season_id else None,
                "status": session.status.value if session.status else None,
                "total_stores": session.total_stores,
                "generated_at": session.generated_at.isoformat() if session.generated_at else None,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "grn": None,
            }
            result.append(session_data)
    
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    session = await db.get(AllocationSession, session_id)
    if session is None or session.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Session not found"})

    lines = await _load_session_lines(session_id, current_user.brand_id, db)
    return envelope({"session": session, "lines": lines})


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
        records.append(
            {
                "GRN Code": grn.grn_code if grn else "",
                "SKU Code": line.get("sku_code", ""),
                "Style Name": line.get("style_name", ""),
                "Size": line.get("sku_size", ""),
                "Store Code": line.get("store_code", ""),
                "Store Name": line.get("store_name", ""),
                "City": line.get("store_city", ""),
                "Quantity": line.get("final_qty")
                if line.get("final_qty") is not None
                else line.get("ai_recommended_qty", 0),
            }
        )

    df = pd.DataFrame(records)
    csv_data = df.to_csv(index=False)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=allocation-{session_id}.csv"},
    )


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
