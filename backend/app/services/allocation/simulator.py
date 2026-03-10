from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InventoryState, Season, SKU, StoreDisplayCapacity


async def simulate_quantity(
    brand_id: UUID, store_id: UUID, sku_id: UUID, quantity: int, db: AsyncSession
) -> dict:
    latest_date_q = await db.execute(
        select(func.max(InventoryState.snapshot_date)).where(InventoryState.brand_id == brand_id)
    )
    latest_date = latest_date_q.scalar_one_or_none()

    state = None
    if latest_date:
        state = await db.scalar(
            select(InventoryState).where(
                InventoryState.brand_id == brand_id,
                InventoryState.snapshot_date == latest_date,
                InventoryState.location_id == str(store_id),
                InventoryState.location_type == "STORE",
                InventoryState.sku_id == sku_id,
            )
        )

    ros_7d = float(state.ros_7d or 0) if state else 0.0
    weeks_cover = quantity / max((ros_7d * 7), 0.01)

    sku = await db.scalar(select(SKU).where(SKU.id == sku_id, SKU.brand_id == brand_id))
    capacity = await db.scalar(
        select(StoreDisplayCapacity).where(
            StoreDisplayCapacity.store_id == store_id,
            StoreDisplayCapacity.category == (sku.category if sku else ""),
        )
    )
    max_units = capacity.max_units if capacity and capacity.max_units is not None else (capacity.max_styles * 6 if capacity else 999)
    remaining_capacity_after = max(max_units - quantity, 0)
    fills_display_capacity = remaining_capacity_after == 0

    season_weeks_remaining = 8
    if sku and sku.season_id:
        season = await db.scalar(select(Season).where(Season.id == sku.season_id))
        if season and season.end_date > date.today():
            season_weeks_remaining = max(1, (season.end_date - date.today()).days // 7)

    projected_sellthrough = min(1.0, weeks_cover / max(season_weeks_remaining, 1))
    stockout_risk = weeks_cover < season_weeks_remaining * 0.7
    overstock_risk = weeks_cover > season_weeks_remaining * 1.3

    notes = "Fills display capacity. No room for follow-up allocation." if fills_display_capacity else "Capacity remains for later top-up allocation."

    return {
        "quantity": quantity,
        "weeks_cover": round(weeks_cover, 1),
        "fills_display_capacity": fills_display_capacity,
        "remaining_capacity_after": int(remaining_capacity_after),
        "projected_sellthrough_eow": round(projected_sellthrough, 2),
        "stockout_risk": stockout_risk,
        "overstock_risk": overstock_risk,
        "notes": notes,
    }
