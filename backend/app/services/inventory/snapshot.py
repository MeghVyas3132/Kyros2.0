from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GRN,
    GRNLine,
    GRNLineReservation,
    InventoryReservationType,
    InventoryState,
    SalesData,
    SKU,
    Store,
)


UPSERT_BATCH_SIZE = 1000


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _inventory_state_upsert_stmt(rows: list[dict]):
    stmt = insert(InventoryState).values(rows)
    return stmt.on_conflict_do_update(
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

    pair_keys = {(str(store_id), sku_id) for store_id, sku_id in pairs}

    latest_inv_rows = await db.execute(
        select(
            InventoryState.location_id,
            InventoryState.sku_id,
            InventoryState.units_on_hand,
        )
        .distinct(InventoryState.location_id, InventoryState.sku_id)
        .where(
            InventoryState.brand_id == brand_id,
            InventoryState.location_type == "STORE",
            InventoryState.snapshot_date <= snapshot_date,
        )
        .order_by(
            InventoryState.location_id,
            InventoryState.sku_id,
            InventoryState.snapshot_date.desc(),
        )
    )
    latest_inv_map: dict[tuple[str, UUID], int] = {}
    for location_id, sku_id, units_on_hand in latest_inv_rows.all():
        latest_inv_map[(location_id, sku_id)] = int(units_on_hand or 0)

    sales_rows = await db.execute(
        select(
            SalesData.store_id,
            SalesData.sku_id,
            func.coalesce(
                func.sum(
                    case((SalesData.week_start_date >= seven_days_ago, SalesData.units_sold), else_=0)
                ),
                0,
            ).label("units_sold_7d"),
            func.coalesce(
                func.sum(
                    case((SalesData.week_start_date >= twenty_eight_days_ago, SalesData.units_sold), else_=0)
                ),
                0,
            ).label("units_sold_28d"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(SalesData.week_start_date >= seven_days_ago, SalesData.was_in_stock.is_(True)),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("in_stock_weeks_7d"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(SalesData.week_start_date >= twenty_eight_days_ago, SalesData.was_in_stock.is_(True)),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("in_stock_weeks_28d"),
            func.coalesce(func.sum(SalesData.units_sold), 0).label("total_sold"),
            func.min(SalesData.week_start_date).label("first_sale_date"),
        )
        .where(
            SalesData.brand_id == brand_id,
            SalesData.week_start_date <= snapshot_date,
        )
        .group_by(SalesData.store_id, SalesData.sku_id)
    )
    sales_map: dict[tuple[str, UUID], dict[str, float | int | date | None]] = {}
    for row in sales_rows.all():
        sales_map[(str(row.store_id), row.sku_id)] = {
            "units_sold_7d": int(row.units_sold_7d or 0),
            "units_sold_28d": int(row.units_sold_28d or 0),
            "in_stock_weeks_7d": int(row.in_stock_weeks_7d or 0),
            "in_stock_weeks_28d": int(row.in_stock_weeks_28d or 0),
            "total_sold": float(row.total_sold or 0),
            "first_sale_date": row.first_sale_date,
        }

    last_grn_rows = await db.execute(
        select(GRNLine.sku_id, func.max(GRN.grn_date))
        .join(GRN, GRNLine.grn_id == GRN.id)
        .where(GRN.brand_id == brand_id, GRNLine.brand_id == brand_id)
        .group_by(GRNLine.sku_id)
    )
    last_grn_map = {sku_id: grn_date for sku_id, grn_date in last_grn_rows.all()}

    upsert_count = 0
    upsert_batch: list[dict] = []

    for location_id, sku_id in pair_keys:
        units_on_hand = int(latest_inv_map.get((location_id, sku_id), 0))
        sales = sales_map.get((location_id, sku_id), {})
        units_sold_7d = int(sales.get("units_sold_7d", 0) or 0)
        units_sold_28d = int(sales.get("units_sold_28d", 0) or 0)
        in_stock_weeks_7d = int(sales.get("in_stock_weeks_7d", 0) or 0)
        in_stock_weeks_28d = int(sales.get("in_stock_weeks_28d", 0) or 0)

        days_in_stock_7d = in_stock_weeks_7d * 7
        days_in_stock_28d = in_stock_weeks_28d * 7
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

        grn_date = last_grn_map.get(sku_id)
        days_since_grn = (snapshot_date - grn_date).days if grn_date else None

        total_sold = float(sales.get("total_sold", 0.0) or 0.0)
        denominator = total_sold + float(units_on_hand)
        sell_through_pct = (total_sold / denominator) if denominator > 0 else None

        first_sale_date = sales.get("first_sale_date")
        days_since_first_sale = (snapshot_date - first_sale_date).days if first_sale_date else None

        upsert_batch.append(
            {
                "brand_id": brand_id,
                "snapshot_date": snapshot_date,
                "location_id": location_id,
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
        upsert_count += 1

        if len(upsert_batch) >= UPSERT_BATCH_SIZE:
            await db.execute(_inventory_state_upsert_stmt(upsert_batch))
            upsert_batch.clear()

    if upsert_batch:
        await db.execute(_inventory_state_upsert_stmt(upsert_batch))

    return upsert_count


async def get_available_for_first_allocation(grn_line_id: UUID, db: AsyncSession) -> int:
    grn_line = await db.get(GRNLine, grn_line_id)
    if grn_line is None:
        return 0

    totals = await db.execute(
        select(
            func.coalesce(func.sum(GRNLineReservation.reserved_qty), 0).label("reserved_sum"),
            func.count(GRNLineReservation.id).label("reservation_count"),
        )
        .join(
            InventoryReservationType,
            and_(
                InventoryReservationType.id == GRNLineReservation.reservation_type_id,
                InventoryReservationType.is_active.is_(True),
                InventoryReservationType.deducts_from_first_allocation.is_(True),
            ),
        )
        .where(GRNLineReservation.grn_line_id == grn_line_id)
    )
    row = totals.one()
    reserved_sum = int(row.reserved_sum or 0)
    reservation_count = int(row.reservation_count or 0)

    if reservation_count == 0:
        reserved_sum = int(grn_line.ecom_reserved_qty or 0) + int(grn_line.ars_reserved_qty or 0)

    available = int(grn_line.units_received or 0) - reserved_sum
    return max(0, available)


async def seed_warehouse_inventory(grn_id: UUID, brand_id: UUID, db: AsyncSession) -> int:
    grn_lines = (
        await db.execute(
            select(GRNLine).where(GRNLine.grn_id == grn_id, GRNLine.brand_id == brand_id)
        )
    ).scalars().all()
    if not grn_lines:
        return 0

    stores = (await db.execute(select(Store).where(Store.brand_id == brand_id))).scalars().all()
    snapshot_date = date.today()
    upsert_count = 0
    upsert_batch: list[dict] = []

    for grn_line in grn_lines:
        available = await get_available_for_first_allocation(grn_line.id, db)
        upsert_batch.append(
            {
                "brand_id": brand_id,
                "snapshot_date": snapshot_date,
                "location_id": "WAREHOUSE-MAIN",
                "location_type": "WAREHOUSE",
                "sku_id": grn_line.sku_id,
                "units_on_hand": int(available),
                "units_in_transit": 0,
                "units_sold_7d": 0,
                "units_sold_28d": 0,
                "ros_7d": None,
                "ros_28d": None,
                "stock_cover_days": None,
                "days_since_grn": None,
                "days_since_first_sale": None,
                "sell_through_pct": None,
                "is_stockout": False,
                "is_new_arrival": False,
            }
        )
        upsert_count += 1

        if len(upsert_batch) >= UPSERT_BATCH_SIZE:
            await db.execute(_inventory_state_upsert_stmt(upsert_batch))
            upsert_batch.clear()

        for store in stores:
            upsert_batch.append(
                {
                    "brand_id": brand_id,
                    "snapshot_date": snapshot_date,
                    "location_id": str(store.id),
                    "location_type": "STORE",
                    "sku_id": grn_line.sku_id,
                    "units_on_hand": 0,
                    "units_in_transit": 0,
                    "units_sold_7d": 0,
                    "units_sold_28d": 0,
                    "ros_7d": None,
                    "ros_28d": None,
                    "stock_cover_days": None,
                    "days_since_grn": None,
                    "days_since_first_sale": None,
                    "sell_through_pct": None,
                    "is_stockout": False,
                    "is_new_arrival": False,
                }
            )
            upsert_count += 1

            if len(upsert_batch) >= UPSERT_BATCH_SIZE:
                await db.execute(_inventory_state_upsert_stmt(upsert_batch))
                upsert_batch.clear()

    if upsert_batch:
        await db.execute(_inventory_state_upsert_stmt(upsert_batch))

    return upsert_count
