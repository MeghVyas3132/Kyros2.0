"""Category × price-band demand bridge.

Two roles in this module:

  1. ``rebuild_bridge_for_brand`` — recompute the entire ``StoreCategoryDemand``
     table for a brand from the current ``SalesData`` rows. Called on every
     successful sales ingestion and from the backfill script. Idempotent.

  2. ``CategoryBridgeCache`` + ``lookup_demand`` — a per-allocation in-memory
     read path that the engine's demand resolver consults after store and
     cluster history miss, before falling back to grade / minimum-presentation.

The aggregation is intentionally simple: we sum ``units_sold`` per
``(store_id, category, price_band)`` across all ``SalesData`` rows and
divide by the number of distinct weeks observed. That gives a stable
weekly ROS that survives synthetic-week spreading. We also count distinct
``sku_id`` so the engine can communicate evidence weight in the reasoning
narrative.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SalesData, SKU, Store, StoreCategoryDemand


_DEFAULT_PRICE_BAND = "*"  # sentinel — matches the column default


def _normalize_band(value: object) -> str:
    if value is None:
        return _DEFAULT_PRICE_BAND
    text = str(value).strip()
    if not text:
        return _DEFAULT_PRICE_BAND
    return text


def _normalize_category(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


# ─── Build path ─────────────────────────────────────────────────────────────


async def rebuild_bridge_for_brand(db: AsyncSession, brand_id: UUID) -> int:
    """Rebuild ``StoreCategoryDemand`` for ``brand_id`` from scratch.

    Returns the number of rows written. The caller commits.
    """
    sku_rows = (
        await db.execute(
            select(SKU.id, SKU.category, SKU.price_band).where(SKU.brand_id == brand_id)
        )
    ).all()
    sku_meta: dict[UUID, tuple[str, str]] = {
        sku_id: (_normalize_category(category), _normalize_band(band))
        for sku_id, category, band in sku_rows
    }

    if not sku_meta:
        # Nothing to aggregate — clear any stale rows.
        await db.execute(
            delete(StoreCategoryDemand).where(StoreCategoryDemand.brand_id == brand_id)
        )
        return 0

    sales_rows = (
        await db.execute(
            select(
                SalesData.store_id,
                SalesData.sku_id,
                SalesData.units_sold,
                SalesData.week_start_date,
            ).where(SalesData.brand_id == brand_id)
        )
    ).all()

    # Aggregator key = (store_id, category, price_band)
    units_sum: dict[tuple[UUID, str, str], int] = defaultdict(int)
    weeks_seen: dict[tuple[UUID, str, str], set] = defaultdict(set)
    skus_seen: dict[tuple[UUID, str, str], set] = defaultdict(set)
    last_week: dict[tuple[UUID, str, str], date | None] = defaultdict(lambda: None)

    for store_id, sku_id, units_sold, week_start_date in sales_rows:
        meta = sku_meta.get(sku_id)
        if meta is None:
            continue
        category, band = meta
        if not category:
            continue
        key = (store_id, category, band)
        units = int(units_sold or 0)
        if units > 0:
            units_sum[key] += units
            skus_seen[key].add(sku_id)
        if week_start_date is not None:
            weeks_seen[key].add(week_start_date)
            current = last_week[key]
            if current is None or week_start_date > current:
                last_week[key] = week_start_date

    # Wipe-and-write keeps the brand's bridge consistent with current sales.
    await db.execute(
        delete(StoreCategoryDemand).where(StoreCategoryDemand.brand_id == brand_id)
    )

    rows_written = 0
    batch: list[StoreCategoryDemand] = []
    for key in set(units_sum.keys()) | set(weeks_seen.keys()):
        store_id, category, band = key
        weeks = max(len(weeks_seen.get(key, set())), 1)
        units = int(units_sum.get(key, 0))
        ros = round(units / weeks, 4)
        if ros <= 0 and units == 0:
            continue
        batch.append(
            StoreCategoryDemand(
                brand_id=brand_id,
                store_id=store_id,
                category=category,
                price_band=band,
                weekly_ros=ros,
                units_observed=units,
                weeks_observed=len(weeks_seen.get(key, set())),
                last_observed_week=last_week.get(key),
                sample_skus=len(skus_seen.get(key, set())),
            )
        )
        rows_written += 1
        if len(batch) >= 500:
            db.add_all(batch)
            await db.flush()
            batch.clear()

    if batch:
        db.add_all(batch)
        await db.flush()

    return rows_written


# ─── Read path ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BridgeHit:
    weekly_ros: float
    units_observed: int
    weeks_observed: int
    sample_skus: int


class CategoryBridgeCache:
    """Per-allocation lookup cache. Loaded once on engine.generate(), then
    served from memory for every (store × sku) decision."""

    def __init__(self) -> None:
        self._exact: dict[tuple[UUID, str, str], BridgeHit] = {}
        self._category_only: dict[tuple[UUID, str], BridgeHit] = {}
        self._loaded = False

    async def load(self, db: AsyncSession, brand_id: UUID) -> int:
        rows = (
            await db.execute(
                select(StoreCategoryDemand).where(
                    StoreCategoryDemand.brand_id == brand_id,
                    StoreCategoryDemand.weekly_ros > 0,
                )
            )
        ).scalars().all()

        # Aggregate to a category-only view (averaged across price bands) so
        # we still have a fallback when the buy file's price_band doesn't
        # match anything seen in sales.
        cat_units: dict[tuple[UUID, str], int] = defaultdict(int)
        cat_weeks: dict[tuple[UUID, str], int] = defaultdict(int)
        cat_skus: dict[tuple[UUID, str], int] = defaultdict(int)

        for row in rows:
            key = (row.store_id, _normalize_category(row.category), _normalize_band(row.price_band))
            self._exact[key] = BridgeHit(
                weekly_ros=float(row.weekly_ros or 0),
                units_observed=int(row.units_observed or 0),
                weeks_observed=int(row.weeks_observed or 0),
                sample_skus=int(row.sample_skus or 0),
            )
            cat_key = (row.store_id, _normalize_category(row.category))
            cat_units[cat_key] += int(row.units_observed or 0)
            cat_weeks[cat_key] = max(cat_weeks[cat_key], int(row.weeks_observed or 0))
            cat_skus[cat_key] += int(row.sample_skus or 0)

        for cat_key, units in cat_units.items():
            weeks = max(cat_weeks.get(cat_key, 0), 1)
            ros = round(units / weeks, 4)
            if ros > 0:
                self._category_only[cat_key] = BridgeHit(
                    weekly_ros=ros,
                    units_observed=units,
                    weeks_observed=cat_weeks.get(cat_key, 0),
                    sample_skus=cat_skus.get(cat_key, 0),
                )

        self._loaded = True
        return len(self._exact)

    def lookup(self, store_id: UUID, category: str | None, price_band: str | None) -> BridgeHit | None:
        if not self._loaded:
            return None
        cat = _normalize_category(category)
        if not cat:
            return None
        band = _normalize_band(price_band)
        hit = self._exact.get((store_id, cat, band))
        if hit is not None:
            return hit
        # Fallback: category at the same store, any band.
        return self._category_only.get((store_id, cat))


# ─── Convenience accessor ──────────────────────────────────────────────────


def keys_overlap(*sources: Iterable[tuple[UUID, str, str]]) -> int:
    """Tiny helper for diagnostics — counts how many keys are common across
    multiple iterables. Used by the bridge backfill script's report line."""
    sets = [set(it) for it in sources]
    if not sets:
        return 0
    return len(set.intersection(*sets))
