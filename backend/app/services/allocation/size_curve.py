from __future__ import annotations

import logging
from typing import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SalesData, SizeGuide, SKU, Store, StoreProductGrade

logger = logging.getLogger(__name__)


def reconcile_weighted_quantities(
    weights: dict[str, float],
    total_units: int,
) -> dict[str, int]:
    """
    Distribute total_units proportionally to weights.
    Handles rounding so output sums exactly to total_units.
    """
    if not weights or total_units <= 0:
        return {}

    positive_weights = {size: max(float(weight), 0.0) for size, weight in weights.items()}
    total_weight = sum(positive_weights.values())
    if total_weight <= 0:
        return {}

    raw = {size: (weight / total_weight) * total_units for size, weight in positive_weights.items()}
    floored = {size: int(quantity) for size, quantity in raw.items()}
    remainder = total_units - sum(floored.values())

    if remainder > 0:
        fractional = sorted(raw.keys(), key=lambda size: raw[size] - floored[size], reverse=True)
        for idx in range(remainder):
            floored[fractional[idx % len(fractional)]] += 1

    return {size: qty for size, qty in floored.items() if qty > 0}


async def load_size_guide(
    brand_id: UUID,
    product_category: str,
    db: AsyncSession,
) -> list[SizeGuide]:
    rows = await db.execute(
        select(SizeGuide)
        .where(
            SizeGuide.brand_id == brand_id,
            SizeGuide.product_category == product_category,
        )
        .order_by(SizeGuide.display_order.asc(), SizeGuide.size.asc())
    )
    return list(rows.scalars().all())


def _normalise_size_ratios(rows: Iterable[tuple[str | None, float | int | None]]) -> dict[str, float]:
    buckets: dict[str, float] = {}
    total_units = 0.0
    for size, units in rows:
        if not size:
            continue
        qty = float(units or 0)
        if qty <= 0:
            continue
        buckets[size] = buckets.get(size, 0.0) + qty
        total_units += qty

    if total_units <= 0:
        return {}
    return {size: qty / total_units for size, qty in buckets.items()}


async def load_historical_size_ratios(
    brand_id: UUID,
    product_category: str,
    store_id: UUID,
    db: AsyncSession,
    historical_season_id: UUID | None = None,
) -> dict[str, float]:
    """
    Fallback chain:
    1. Store-level ratios
    2. Cluster-level ratios
    3. Brand-level ratios
    4. Empty dict (caller should use guide weights only)
    """
    store_rows = await db.execute(
        select(SKU.size, func.sum(SalesData.units_sold))
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SalesData.store_id == store_id,
            SKU.category == product_category,
            *( [SalesData.season_id == historical_season_id] if historical_season_id is not None else [] ),
        )
        .group_by(SKU.size)
    )
    store_ratios = _normalise_size_ratios(store_rows.all())
    if store_ratios:
        return store_ratios

    cluster_id = await db.scalar(
        select(Store.cluster_id).where(
            Store.id == store_id,
            Store.brand_id == brand_id,
        )
    )
    if cluster_id is not None:
        cluster_rows = await db.execute(
            select(SKU.size, func.sum(SalesData.units_sold))
            .join(SKU, SKU.id == SalesData.sku_id)
            .join(Store, Store.id == SalesData.store_id)
            .where(
                SalesData.brand_id == brand_id,
                Store.cluster_id == cluster_id,
                SKU.category == product_category,
                *( [SalesData.season_id == historical_season_id] if historical_season_id is not None else [] ),
            )
            .group_by(SKU.size)
        )
        cluster_ratios = _normalise_size_ratios(cluster_rows.all())
        if cluster_ratios:
            return cluster_ratios

    brand_rows = await db.execute(
        select(SKU.size, func.sum(SalesData.units_sold))
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SKU.category == product_category,
            *( [SalesData.season_id == historical_season_id] if historical_season_id is not None else [] ),
        )
        .group_by(SKU.size)
    )
    brand_ratios = _normalise_size_ratios(brand_rows.all())
    if brand_ratios:
        return brand_ratios

    logger.warning(
        "No historical size data found for brand=%s product_category=%s store=%s. Using size-guide ratios only.",
        brand_id,
        product_category,
        store_id,
    )
    return {}


async def distribute_size_sets(
    brand_id: UUID,
    product_category: str,
    store_id: UUID,
    total_units: int,
    eligible_guides: list[SizeGuide],
    db: AsyncSession,
    historical_season_id: UUID | None = None,
) -> dict[str, int]:
    """
    For products where sizes are combined sets (for example S/M and L/XL).
    Uses store->cluster->brand historical set ratios with fallback to guide weights.
    """
    if total_units <= 0:
        return {}

    set_guides = [guide for guide in eligible_guides if guide.is_size_set]
    guides = set_guides or eligible_guides
    if not guides:
        return {}

    historical = await load_historical_size_ratios(
        brand_id=brand_id,
        product_category=product_category,
        store_id=store_id,
        db=db,
        historical_season_id=historical_season_id,
    )

    weights: dict[str, float] = {}
    for guide in guides:
        size = guide.size
        if historical.get(size, 0) > 0:
            weights[size] = historical[size]
        else:
            weights[size] = float(max(guide.min_max_ratio, 1))

    return reconcile_weighted_quantities(weights, total_units)


def _size_allowed_for_grade(applies_to_grades: str, store_grade: str) -> bool:
    if applies_to_grades == "ALL":
        return True
    if applies_to_grades == "A+_ONLY":
        return store_grade == "A+"
    if applies_to_grades == "A+_A":
        return store_grade in {"A+", "A"}
    if applies_to_grades == "A+_A_B":
        return store_grade in {"A+", "A", "B"}
    return True


async def calculate_size_distribution(
    db: AsyncSession,
    brand_id: UUID,
    sku: SKU | None = None,
    store: Store | None = None,
    total_qty: int | None = None,
    *,
    product_category: str | None = None,
    store_id: UUID | None = None,
    store_grade: str | None = None,
    total_units: int | None = None,
    historical_season_id: UUID | None = None,
) -> dict[str, int]:
    """
    Generic size distribution:
    1. Load size guide
    2. Keep sizes eligible for this grade and with ratio > 0
    3. Use historical size ratios to adjust guide weights when available
    4. Reconcile to exact total_units
    """
    resolved_category = product_category or (sku.category if sku is not None else None)
    resolved_store_id = store_id or (store.id if store is not None else None)
    resolved_total_units = total_units if total_units is not None else total_qty

    if resolved_category is None or resolved_store_id is None or resolved_total_units is None:
        return {}

    if resolved_total_units <= 0:
        return {}

    resolved_store_grade = store_grade
    if not resolved_store_grade:
        resolved_store_grade = await db.scalar(
            select(StoreProductGrade.grade).where(
                StoreProductGrade.brand_id == brand_id,
                StoreProductGrade.store_id == resolved_store_id,
                StoreProductGrade.product_category == resolved_category,
            )
        )
    resolved_store_grade = (resolved_store_grade or "C").upper()

    guides = await load_size_guide(brand_id, resolved_category, db)
    if not guides:
        return {}

    eligible = [
        guide
        for guide in guides
        if guide.min_max_ratio > 0 and _size_allowed_for_grade(guide.applies_to_grades, resolved_store_grade)
    ]
    if not eligible:
        return {}

    if len(eligible) == 1 and eligible[0].size.upper() in {"FS", "FREE SIZE", "ONE SIZE"}:
        return {eligible[0].size: resolved_total_units}

    if any(guide.is_size_set for guide in eligible):
        return await distribute_size_sets(
            brand_id=brand_id,
            product_category=resolved_category,
            store_id=resolved_store_id,
            total_units=resolved_total_units,
            eligible_guides=eligible,
            db=db,
            historical_season_id=historical_season_id,
        )

    historical = await load_historical_size_ratios(
        brand_id=brand_id,
        product_category=resolved_category,
        store_id=resolved_store_id,
        db=db,
        historical_season_id=historical_season_id,
    )
    base_weights = {guide.size: float(guide.min_max_ratio) for guide in eligible}
    total_base = sum(base_weights.values()) or 1.0

    adjusted: dict[str, float] = {}
    for size, base in base_weights.items():
        expected_ratio = base / total_base
        observed_ratio = historical.get(size)
        if observed_ratio and expected_ratio > 0:
            adjustment = min(observed_ratio / expected_ratio, 1.5)
            adjusted[size] = base * adjustment
        else:
            adjusted[size] = base

    return reconcile_weighted_quantities(adjusted, resolved_total_units)
