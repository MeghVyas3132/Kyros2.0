from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GRN, GRNLine, InventoryState, SalesData, SKU, Store


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


async def build_snapshot_for_brand(brand_id: UUID, snapshot_date: date, db: AsyncSession) -> int:
    ninety_days_ago = snapshot_date - timedelta(days=90)
    seven_days_ago = snapshot_date - timedelta(days=7)
    twenty_eight_days_ago = snapshot_date - timedelta(days=28)

    sales_activity = await db.execute(
        select(SalesData.store_id, SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SalesData.week_start_date >= ninety_days_ago,
            SalesData.week_start_date <= snapshot_date,
        )
        .group_by(SalesData.store_id, SalesData.sku_id)
    )
    pairs = {(store_id, sku_id) for store_id, sku_id in sales_activity.all()}

    inv_activity = await db.execute(
        select(InventoryState.location_id, InventoryState.sku_id)
        .where(
            InventoryState.brand_id == brand_id,
            InventoryState.snapshot_date >= ninety_days_ago,
            InventoryState.snapshot_date <= snapshot_date,
            InventoryState.location_type == "STORE",
        )
        .group_by(InventoryState.location_id, InventoryState.sku_id)
    )
    for location_id, sku_id in inv_activity.all():
        try:
            pairs.add((UUID(location_id), sku_id))
        except ValueError:
            continue

    if not pairs:
        return 0

    upsert_rows = []
    for store_id, sku_id in pairs:
        recent_inv = await db.execute(
            select(InventoryState)
            .where(
                InventoryState.brand_id == brand_id,
                InventoryState.location_type == "STORE",
                InventoryState.location_id == str(store_id),
                InventoryState.sku_id == sku_id,
                InventoryState.snapshot_date <= snapshot_date,
            )
            .order_by(InventoryState.snapshot_date.desc())
            .limit(1)
        )
        latest_inv = recent_inv.scalar_one_or_none()
        units_on_hand = latest_inv.units_on_hand if latest_inv else 0

        sales_7d = await db.execute(
            select(
                func.coalesce(func.sum(SalesData.units_sold), 0),
                func.count(func.nullif(SalesData.was_in_stock, False)),
            ).where(
                SalesData.brand_id == brand_id,
                SalesData.store_id == store_id,
                SalesData.sku_id == sku_id,
                SalesData.week_start_date >= seven_days_ago,
                SalesData.week_start_date <= snapshot_date,
            )
        )
        units_sold_7d, in_stock_weeks_7d = sales_7d.one()

        sales_28d = await db.execute(
            select(
                func.coalesce(func.sum(SalesData.units_sold), 0),
                func.count(func.nullif(SalesData.was_in_stock, False)),
            ).where(
                SalesData.brand_id == brand_id,
                SalesData.store_id == store_id,
                SalesData.sku_id == sku_id,
                SalesData.week_start_date >= twenty_eight_days_ago,
                SalesData.week_start_date <= snapshot_date,
            )
        )
        units_sold_28d, in_stock_weeks_28d = sales_28d.one()

        days_in_stock_7d = int(in_stock_weeks_7d or 0) * 7
        days_in_stock_28d = int(in_stock_weeks_28d or 0) * 7
        ros_7d = _safe_div(float(units_sold_7d), max(days_in_stock_7d, 1))
        ros_28d = _safe_div(float(units_sold_28d), max(days_in_stock_28d, 1))

        if units_on_hand == 0 and (ros_7d or 0) > 0:
            stock_cover_days = 0.0
        elif ros_7d is None or ros_7d <= 0:
            stock_cover_days = None
        elif ros_7d < 0.01:
            stock_cover_days = float(units_on_hand) / 0.01
        else:
            stock_cover_days = float(units_on_hand) / ros_7d

        latest_grn = await db.execute(
            select(func.max(GRN.grn_date))
            .join(GRNLine, GRNLine.grn_id == GRN.id)
            .where(
                GRN.brand_id == brand_id,
                GRNLine.brand_id == brand_id,
                GRNLine.sku_id == sku_id,
            )
        )
        grn_date = latest_grn.scalar_one_or_none()
        days_since_grn = (snapshot_date - grn_date).days if grn_date else None

        total_sold_q = await db.execute(
            select(func.coalesce(func.sum(SalesData.units_sold), 0)).where(
                SalesData.brand_id == brand_id,
                SalesData.store_id == store_id,
                SalesData.sku_id == sku_id,
            )
        )
        total_sold = float(total_sold_q.scalar_one() or 0)
        denominator = total_sold + float(units_on_hand)
        sell_through_pct = (total_sold / denominator) if denominator > 0 else None

        first_sale_q = await db.execute(
            select(func.min(SalesData.week_start_date)).where(
                SalesData.brand_id == brand_id,
                SalesData.store_id == store_id,
                SalesData.sku_id == sku_id,
            )
        )
        first_sale_date = first_sale_q.scalar_one_or_none()
        days_since_first_sale = (snapshot_date - first_sale_date).days if first_sale_date else None

        upsert_rows.append(
            {
                "brand_id": brand_id,
                "snapshot_date": snapshot_date,
                "location_id": str(store_id),
                "location_type": "STORE",
                "sku_id": sku_id,
                "units_on_hand": int(units_on_hand),
                "units_in_transit": 0,
                "units_sold_7d": int(units_sold_7d or 0),
                "units_sold_28d": int(units_sold_28d or 0),
                "ros_7d": round(ros_7d, 3) if ros_7d is not None else None,
                "ros_28d": round(ros_28d, 3) if ros_28d is not None else None,
                "stock_cover_days": round(stock_cover_days, 1) if stock_cover_days is not None else None,
                "days_since_grn": days_since_grn,
                "days_since_first_sale": days_since_first_sale,
                "sell_through_pct": round(sell_through_pct, 2) if sell_through_pct is not None else None,
                "is_stockout": units_on_hand == 0 and (ros_7d or 0) > 0,
                "is_new_arrival": days_since_grn is not None and days_since_grn <= 14,
            }
        )

    if upsert_rows:
        stmt = insert(InventoryState).values(upsert_rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_inventory_state_unique",
            set_={
                "units_on_hand": stmt.excluded.units_on_hand,
                "units_in_transit": stmt.excluded.units_in_transit,
                "units_sold_7d": stmt.excluded.units_sold_7d,
                "units_sold_28d": stmt.excluded.units_sold_28d,
                "ros_7d": stmt.excluded.ros_7d,
                "ros_28d": stmt.excluded.ros_28d,
                "stock_cover_days": stmt.excluded.stock_cover_days,
                "days_since_grn": stmt.excluded.days_since_grn,
                "days_since_first_sale": stmt.excluded.days_since_first_sale,
                "sell_through_pct": stmt.excluded.sell_through_pct,
                "is_stockout": stmt.excluded.is_stockout,
                "is_new_arrival": stmt.excluded.is_new_arrival,
            },
        )
        await db.execute(stmt)

    return len(upsert_rows)
