from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SalesData, SizeGuide, SKU, Store

logger = logging.getLogger(__name__)


@dataclass
class PreloadedSizeRatios:
    store_ratios: dict[tuple[UUID, str], dict[str, float]]
    cluster_ratios: dict[tuple[UUID, str], dict[str, float]]
    brand_ratios: dict[str, dict[str, float]]


async def preload_size_data(brand_id: UUID, db: AsyncSession) -> tuple[dict[str, list[SizeGuide]], PreloadedSizeRatios]:
    guides_rows = await db.execute(
        select(SizeGuide)
        .where(SizeGuide.brand_id == brand_id)
        .order_by(SizeGuide.display_order.asc(), SizeGuide.size.asc())
    )
    
    guides: dict[str, list[SizeGuide]] = {}
    for guide in guides_rows.scalars().all():
        cat = " ".join(str(guide.product_category or "").strip().lower().split())
        guides.setdefault(cat, []).append(guide)
        
    ratios_rows = await db.execute(
        select(
            SalesData.store_id,
            Store.cluster_id,
            SKU.category,
            SKU.size,
            func.sum(SalesData.units_sold).label("units")
        )
        .join(SKU, SKU.id == SalesData.sku_id)
        .join(Store, Store.id == SalesData.store_id)
        .where(SalesData.brand_id == brand_id, Store.brand_id == brand_id)
        .group_by(SalesData.store_id, Store.cluster_id, SKU.category, SKU.size)
    )

    store_ratios: dict[tuple[UUID, str], dict[str, float]] = {}
    cluster_ratios: dict[tuple[UUID, str], dict[str, float]] = {}
    brand_ratios: dict[str, dict[str, float]] = {}

    for store_id, cluster_id, category, size, units in ratios_rows.all():
        if not category or not size or units is None:
            continue
        units_val = float(units)
        if units_val <= 0:
            continue
            
        norm_cat = " ".join(str(category).strip().lower().split())

        store_key = (store_id, norm_cat)
        if store_key not in store_ratios:
            store_ratios[store_key] = {}
        store_ratios[store_key][size] = store_ratios[store_key].get(size, 0.0) + units_val

        if cluster_id is not None:
            cluster_key = (cluster_id, norm_cat)
            if cluster_key not in cluster_ratios:
                cluster_ratios[cluster_key] = {}
            cluster_ratios[cluster_key][size] = cluster_ratios[cluster_key].get(size, 0.0) + units_val

        if norm_cat not in brand_ratios:
            brand_ratios[norm_cat] = {}
        brand_ratios[norm_cat][size] = brand_ratios[norm_cat].get(size, 0.0) + units_val

    def _norm(dct):
        for k, sizes in dct.items():
            total = sum(sizes.values())
            if total > 0:
                dct[k] = {s: qty / total for s, qty in sizes.items()}
    
    _norm(store_ratios)
    _norm(cluster_ratios)
    _norm(brand_ratios)

    return guides, PreloadedSizeRatios(
        store_ratios=store_ratios,
        cluster_ratios=cluster_ratios,
        brand_ratios=brand_ratios,
    )


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


def load_historical_size_ratios(
    brand_id: UUID,
    product_category: str,
    store_id: UUID,
    store_cluster_id: UUID | None,
    preloaded_ratios: PreloadedSizeRatios,
) -> dict[str, float]:
    norm_cat = " ".join(str(product_category).strip().lower().split())
    
    store_res = preloaded_ratios.store_ratios.get((store_id, norm_cat))
    if store_res:
        return store_res
    
    if store_cluster_id is not None:
        cluster_res = preloaded_ratios.cluster_ratios.get((store_cluster_id, norm_cat))
        if cluster_res:
            return cluster_res
            
    brand_res = preloaded_ratios.brand_ratios.get(norm_cat)
    if brand_res:
        return brand_res
        
    logger.warning(
        "No historical size data found for brand=%s product_category=%s store=%s. Using size-guide ratios only.",
        brand_id,
        product_category,
        store_id,
    )
    return {}


def distribute_size_sets(
    brand_id: UUID,
    product_category: str,
    store_id: UUID,
    store_cluster_id: UUID | None,
    total_units: int,
    eligible_guides: list[SizeGuide],
    preloaded_ratios: PreloadedSizeRatios,
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

    historical = load_historical_size_ratios(
        brand_id=brand_id,
        product_category=product_category,
        store_id=store_id,
        store_cluster_id=store_cluster_id,
        preloaded_ratios=preloaded_ratios,
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
    preloaded_guides: dict[str, list[SizeGuide]] | None = None,
    preloaded_ratios: PreloadedSizeRatios | None = None,
) -> dict[str, int]:
    """
    Generic size distribution using RAM caches.
    """
    resolved_category = product_category or (sku.category if sku is not None else None)
    resolved_store = store
    resolved_store_id = store_id or (store.id if store is not None else None)
    resolved_total_units = total_units if total_units is not None else total_qty

    if resolved_category is None or resolved_store_id is None or resolved_total_units is None:
        return {}

    if resolved_total_units is None or resolved_total_units <= 0:
        return {}

    resolved_store_grade = (store_grade or "C").upper()
    norm_cat = " ".join(str(resolved_category).strip().lower().split())

    guides = preloaded_guides.get(norm_cat, []) if preloaded_guides else []
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
        return {eligible[0].size: int(resolved_total_units)}

    if any(guide.is_size_set for guide in eligible):
        return distribute_size_sets(
            brand_id=brand_id,
            product_category=resolved_category,
            store_id=resolved_store_id,
            store_cluster_id=resolved_store.cluster_id if resolved_store else None,
            total_units=int(resolved_total_units),
            eligible_guides=eligible,
            preloaded_ratios=preloaded_ratios,
        ) if preloaded_ratios else {}

    historical = load_historical_size_ratios(
        brand_id=brand_id,
        product_category=resolved_category,
        store_id=resolved_store_id,
        store_cluster_id=resolved_store.cluster_id if resolved_store else None,
        preloaded_ratios=preloaded_ratios,
    ) if preloaded_ratios else {}

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

    return reconcile_weighted_quantities(adjusted, int(resolved_total_units))

