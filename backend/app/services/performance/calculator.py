from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InventoryState, PerformanceSnapshot, Season, SKU, Store


def classify_style_status(
    sell_through_pct: float | None,
    stock_cover_days: float | None,
    days_since_grn: int | None,
    season_start: date,
    season_end: date,
) -> str:
    today = date.today()
    season_days = max((season_end - season_start).days, 1)
    elapsed = max((today - season_start).days, 0)
    pct_season_elapsed = min(elapsed / season_days, 1.0)

    st = sell_through_pct or 0
    cover = stock_cover_days if stock_cover_days is not None else 999
    age = days_since_grn or 0

    if age > 60 and st < 0.20:
        return "CRITICAL"
    if st < (pct_season_elapsed * 0.6):
        return "PROBLEM"
    if cover > 42 or st < (pct_season_elapsed * 0.8):
        return "WATCH"
    return "HEALTHY"


def _chunked(rows: list[dict], size: int = 1000):
    for idx in range(0, len(rows), size):
        yield rows[idx : idx + size]


async def build_performance_snapshots(brand_id: UUID, snapshot_date: date, db: AsyncSession) -> int:
    season = await db.scalar(
        select(Season)
        .where(Season.brand_id == brand_id, Season.status == "ACTIVE")
        .order_by(Season.start_date.desc())
    )

    if season is None:
        season = await db.scalar(
            select(Season).where(Season.brand_id == brand_id).order_by(Season.start_date.desc())
        )
    if season is None:
        return 0

    latest_inv_date_q = await db.execute(
        select(func.max(InventoryState.snapshot_date)).where(InventoryState.brand_id == brand_id)
    )
    latest_inv_date = latest_inv_date_q.scalar_one_or_none()
    if latest_inv_date is None:
        return 0

    inv_rows = (
        await db.execute(
            select(InventoryState).where(
                InventoryState.brand_id == brand_id,
                InventoryState.snapshot_date == latest_inv_date,
                InventoryState.location_type == "STORE",
            )
        )
    ).scalars().all()

    rows = []
    for inv in inv_rows:
        style_status = classify_style_status(
            float(inv.sell_through_pct) if inv.sell_through_pct is not None else None,
            float(inv.stock_cover_days) if inv.stock_cover_days is not None else None,
            inv.days_since_grn,
            season.start_date,
            season.end_date,
        )
        rows.append(
            {
                "brand_id": brand_id,
                "snapshot_date": snapshot_date,
                "season_id": season.id,
                "store_id": UUID(inv.location_id),
                "sku_id": inv.sku_id,
                "units_sold_today": 0,
                "units_sold_7d": inv.units_sold_7d,
                "units_sold_28d": inv.units_sold_28d,
                "units_on_hand": inv.units_on_hand,
                "sell_through_pct": inv.sell_through_pct,
                "ros_7d": inv.ros_7d,
                "stock_cover_days": inv.stock_cover_days,
                "days_since_grn": inv.days_since_grn,
                "style_status": style_status,
                "is_stockout": inv.is_stockout,
                "lost_sales_estimate": float(inv.ros_7d or 0) * 7 if inv.is_stockout else 0,
            }
        )

    if rows:
        for batch in _chunked(rows):
            stmt = insert(PerformanceSnapshot).values(batch)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_perf_snapshot_brand_date_store_sku",
                set_={
                    "units_sold_today": stmt.excluded.units_sold_today,
                    "units_sold_7d": stmt.excluded.units_sold_7d,
                    "units_sold_28d": stmt.excluded.units_sold_28d,
                    "units_on_hand": stmt.excluded.units_on_hand,
                    "sell_through_pct": stmt.excluded.sell_through_pct,
                    "ros_7d": stmt.excluded.ros_7d,
                    "stock_cover_days": stmt.excluded.stock_cover_days,
                    "days_since_grn": stmt.excluded.days_since_grn,
                    "style_status": stmt.excluded.style_status,
                    "is_stockout": stmt.excluded.is_stockout,
                    "lost_sales_estimate": stmt.excluded.lost_sales_estimate,
                },
            )
            await db.execute(stmt)

    return len(rows)
