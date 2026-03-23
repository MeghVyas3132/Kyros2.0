from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertType, AllocationLine, AllocationSession, AllocationStatus, GRN, InventoryState


async def _has_active_duplicate(
    db: AsyncSession,
    brand_id: UUID,
    alert_type: AlertType,
    store_id: UUID | None,
    sku_id: UUID | None,
    grn_id: UUID | None,
) -> bool:
    existing = await db.execute(
        select(Alert).where(
            Alert.brand_id == brand_id,
            Alert.alert_type == alert_type,
            Alert.store_id == store_id,
            Alert.sku_id == sku_id,
            Alert.grn_id == grn_id,
            Alert.is_read.is_(False),
            Alert.is_dismissed.is_(False),
        )
    )
    return existing.scalar_one_or_none() is not None


async def generate_alerts(brand_id: UUID, run_date: date, db: AsyncSession) -> int:
    created = 0

    latest_date_q = await db.execute(
        select(func.max(InventoryState.snapshot_date)).where(InventoryState.brand_id == brand_id)
    )
    latest_date = latest_date_q.scalar_one_or_none()
    if latest_date is None:
        return 0

    stockout_risk_rows = (
        await db.execute(
            select(InventoryState).where(
                InventoryState.brand_id == brand_id,
                InventoryState.snapshot_date == latest_date,
                InventoryState.location_type == "STORE",
                InventoryState.units_on_hand > 0,
                InventoryState.stock_cover_days < 7,
                InventoryState.ros_7d > 0.1,
            )
        )
    ).scalars().all()

    for row in stockout_risk_rows:
        store_id = UUID(row.location_id)
        if await _has_active_duplicate(
            db, brand_id, AlertType.STOCKOUT_RISK, store_id, row.sku_id, None
        ):
            continue
        db.add(
            Alert(
                brand_id=brand_id,
                alert_type=AlertType.STOCKOUT_RISK,
                severity="HIGH",
                title="Stockout risk in under 7 days",
                message="High velocity SKU may stock out soon.",
                store_id=store_id,
                sku_id=row.sku_id,
                action_url=f"/performance/styles?store_id={store_id}",
                generated_at=func.now(),
            )
        )
        created += 1

    aging_rows = (
        await db.execute(
            select(InventoryState).where(
                InventoryState.brand_id == brand_id,
                InventoryState.snapshot_date == latest_date,
                InventoryState.location_type == "STORE",
                InventoryState.days_since_grn > 45,
                InventoryState.sell_through_pct < 0.25,
            )
        )
    ).scalars().all()

    for row in aging_rows:
        store_id = UUID(row.location_id)
        if await _has_active_duplicate(db, brand_id, AlertType.AGING_STOCK, store_id, row.sku_id, None):
            continue
        db.add(
            Alert(
                brand_id=brand_id,
                alert_type=AlertType.AGING_STOCK,
                severity="MEDIUM",
                title="Aging stock needs action",
                message="SKU has been in store for 45+ days with low sell-through.",
                store_id=store_id,
                sku_id=row.sku_id,
                action_url=f"/performance/styles?store_id={store_id}&status=PROBLEM",
                generated_at=func.now(),
            )
        )
        created += 1

    threshold_date = run_date - timedelta(days=14)
    grn_rows = (
        await db.execute(
            select(GRN).where(
                GRN.brand_id == brand_id,
                GRN.created_at <= threshold_date,
                GRN.status == "RECEIVED",
            )
        )
    ).scalars().all()

    for grn in grn_rows:
        alloc_exists = await db.execute(
            select(AllocationSession).where(
                AllocationSession.brand_id == brand_id,
                AllocationSession.grn_id == grn.id,
                AllocationSession.status == "APPROVED",
            )
        )
        if alloc_exists.scalar_one_or_none() is not None:
            continue

        if await _has_active_duplicate(db, brand_id, AlertType.GRN_UNALLOCATED, None, None, grn.id):
            continue

        db.add(
            Alert(
                brand_id=brand_id,
                alert_type=AlertType.GRN_UNALLOCATED,
                severity="HIGH",
                title="GRN not allocated",
                message="GRN is older than 14 days and still unallocated.",
                grn_id=grn.id,
                action_url=f"/grn/{grn.id}",
                generated_at=func.now(),
            )
        )
        created += 1

    warehouse_rows = (
        await db.execute(
            select(InventoryState).where(
                InventoryState.brand_id == brand_id,
                InventoryState.snapshot_date == latest_date,
                InventoryState.location_type == "WAREHOUSE",
                InventoryState.units_on_hand > 0,
            )
        )
    ).scalars().all()
    for row in warehouse_rows:
        if await _has_active_duplicate(
            db,
            brand_id,
            AlertType.WAREHOUSE_STOCK_SITTING,
            None,
            row.sku_id,
            None,
        ):
            continue
        db.add(
            Alert(
                brand_id=brand_id,
                alert_type=AlertType.WAREHOUSE_STOCK_SITTING,
                severity="MEDIUM",
                title="Warehouse stock sitting unallocated",
                message="Warehouse has stock that is not yet flowing to stores.",
                sku_id=row.sku_id,
                action_url="/allocation",
                generated_at=func.now(),
            )
        )
        created += 1

    high_cover_rows = (
        await db.execute(
            select(AllocationLine)
            .join(AllocationSession, AllocationSession.id == AllocationLine.session_id)
            .where(
                AllocationLine.brand_id == brand_id,
                AllocationSession.brand_id == brand_id,
                AllocationSession.status.in_([AllocationStatus.UNDER_REVIEW, AllocationStatus.APPROVED]),
            )
        )
    ).scalars().all()
    for line in high_cover_rows:
        reasoning = line.ai_reasoning or {}
        weeks_cover = float(reasoning.get("weeks_cover_at_recommended") or 0)
        target_cover = float(reasoning.get("cover_target_weeks") or 0)
        if target_cover <= 0:
            continue
        if weeks_cover <= target_cover * 1.5:
            continue
        if await _has_active_duplicate(db, brand_id, AlertType.HIGH_COVER, line.store_id, line.sku_id, None):
            continue
        db.add(
            Alert(
                brand_id=brand_id,
                alert_type=AlertType.HIGH_COVER,
                severity="MEDIUM",
                title="High cover allocation",
                message=(
                    f"Allocated cover ({weeks_cover:.1f}w) exceeds target ({target_cover:.1f}w) by more than 50%."
                ),
                store_id=line.store_id,
                sku_id=line.sku_id,
                action_url="/allocation",
                generated_at=func.now(),
            )
        )
        created += 1

    return created
