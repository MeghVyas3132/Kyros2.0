from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SalesData, SKU, Store, StoreBehaviorProfile
from app.utils.date_utils import utcnow


@dataclass
class ProfileSignal:
    category_affinity: str | None
    fabric_affinity: str | None
    category_affinity_score: float | None
    fabric_affinity_score: float | None
    sample_size: int


class VelocityArchetype(str, Enum):
    FAST_BURN = "Fast Burn"
    STEADY = "Steady"
    LATE_BLOOMER = "Late Bloomer"
    ERRATIC = "Erratic"
    STAGNANT = "Stagnant"


def _calculate_affinity(
    store_dim: dict[str, float],
    store_total: float,
    brand_dim: dict[str, float],
    brand_total: float,
) -> dict[str, float]:
    """
    Affinity = store share of a dimension / brand average share.
    >1.0 means over-indexing.
    """
    if store_total <= 0 or brand_total <= 0:
        return {}

    result: dict[str, float] = {}
    for key, store_sold in store_dim.items():
        store_share = float(store_sold or 0) / store_total
        brand_share = float(brand_dim.get(key, 0.0) or 0.0) / brand_total
        if brand_share > 0:
            result[key] = round(store_share / brand_share, 3)
    return result


def _classify_velocity_archetype(weekly_units: list[float]) -> VelocityArchetype:
    if not weekly_units:
        return VelocityArchetype.STAGNANT

    mean_units = sum(weekly_units) / len(weekly_units)
    if mean_units < 1.0:
        return VelocityArchetype.STAGNANT

    variance = sum((x - mean_units) ** 2 for x in weekly_units) / len(weekly_units)
    std_dev = variance ** 0.5
    cv = (std_dev / mean_units) if mean_units > 0 else 0.0
    if cv > 0.8:
        return VelocityArchetype.ERRATIC

    total_units = sum(weekly_units)
    if total_units <= 0:
        return VelocityArchetype.STAGNANT

    first_three = sum(weekly_units[:3])
    last_three = sum(weekly_units[-3:])
    first_share = first_three / total_units
    last_share = last_three / total_units

    if first_share > 0.40:
        return VelocityArchetype.FAST_BURN
    if first_share < 0.20 and last_share > 0.40:
        return VelocityArchetype.LATE_BLOOMER
    return VelocityArchetype.STEADY


async def load_store_profile_map(brand_id: UUID, db: AsyncSession) -> dict[UUID, ProfileSignal]:
    rows = (
        await db.execute(
            select(StoreBehaviorProfile).where(StoreBehaviorProfile.brand_id == brand_id)
        )
    ).scalars().all()
    return {
        row.store_id: ProfileSignal(
            category_affinity=row.primary_category_affinity,
            fabric_affinity=row.primary_fabric_affinity,
            category_affinity_score=row.category_affinity_score,
            fabric_affinity_score=row.fabric_affinity_score,
            sample_size=int(row.sample_size or 0),
        )
        for row in rows
    }


async def refresh_store_profiles(brand_id: UUID, db: AsyncSession, lookback_weeks: int = 12) -> int:
    end_date = utcnow().date()
    start_date = end_date - timedelta(weeks=max(lookback_weeks, 1))

    category_rows = (
        await db.execute(
            select(
                SalesData.store_id,
                SKU.category,
                func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
            )
            .join(SKU, SKU.id == SalesData.sku_id)
            .where(
                SalesData.brand_id == brand_id,
                SalesData.week_start_date >= start_date,
                SalesData.week_start_date <= end_date,
            )
            .group_by(SalesData.store_id, SKU.category)
        )
    ).all()

    fabric_rows = (
        await db.execute(
            select(
                SalesData.store_id,
                SKU.fabric,
                func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
            )
            .join(SKU, SKU.id == SalesData.sku_id)
            .where(
                SalesData.brand_id == brand_id,
                SalesData.week_start_date >= start_date,
                SalesData.week_start_date <= end_date,
            )
            .group_by(SalesData.store_id, SKU.fabric)
        )
    ).all()

    by_store_category: dict[UUID, dict[str, float]] = defaultdict(dict)
    by_store_fabric: dict[UUID, dict[str, float]] = defaultdict(dict)

    for store_id, category, units in category_rows:
        if category:
            by_store_category[store_id][str(category)] = float(units or 0)

    for store_id, fabric, units in fabric_rows:
        if fabric:
            by_store_fabric[store_id][str(fabric)] = float(units or 0)

    store_ids = set(by_store_category.keys()) | set(by_store_fabric.keys())
    if not store_ids:
        return 0

    existing_rows = (
        await db.execute(
            select(StoreBehaviorProfile).where(
                and_(
                    StoreBehaviorProfile.brand_id == brand_id,
                    StoreBehaviorProfile.store_id.in_(list(store_ids)),
                )
            )
        )
    ).scalars().all()
    existing = {row.store_id: row for row in existing_rows}

    upserts = 0
    for store_id in store_ids:
        category_bucket = by_store_category.get(store_id, {})
        fabric_bucket = by_store_fabric.get(store_id, {})

        total_category_units = sum(category_bucket.values())
        total_fabric_units = sum(fabric_bucket.values())

        top_category = max(category_bucket.items(), key=lambda item: item[1])[0] if category_bucket else None
        top_fabric = max(fabric_bucket.items(), key=lambda item: item[1])[0] if fabric_bucket else None

        category_score = (
            round(category_bucket[top_category] / total_category_units, 4)
            if top_category and total_category_units > 0
            else None
        )
        fabric_score = (
            round(fabric_bucket[top_fabric] / total_fabric_units, 4)
            if top_fabric and total_fabric_units > 0
            else None
        )

        sample_size = int(max(total_category_units, total_fabric_units, 0))

        row = existing.get(store_id)
        now = utcnow()
        if row is None:
            row = StoreBehaviorProfile(
                brand_id=brand_id,
                store_id=store_id,
                created_at=now,
                updated_at=now,
            )
            db.add(row)

        row.primary_category_affinity = top_category
        row.primary_fabric_affinity = top_fabric
        row.category_affinity_score = category_score
        row.fabric_affinity_score = fabric_score
        row.profile_window_weeks = max(lookback_weeks, 1)
        row.sample_size = sample_size
        row.updated_at = now
        upserts += 1

    await db.flush()
    return upserts


async def build_all_store_profiles(
    db: AsyncSession,
    brand_id: UUID,
    season_id: UUID,
) -> int:
    """
    Build store behavior profiles for all active stores in a season.
    Uses seasonal sales history and writes one profile row per active store.
    """
    active_store_rows = (
        await db.execute(
            select(Store.id)
            .where(Store.brand_id == brand_id, Store.is_active.is_(True))
        )
    ).all()
    active_store_ids = [row.id for row in active_store_rows]
    if not active_store_ids:
        return 0

    category_rows = (
        await db.execute(
            select(
                SalesData.store_id,
                SKU.category,
                func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
            )
            .join(SKU, SKU.id == SalesData.sku_id)
            .where(
                SalesData.brand_id == brand_id,
                SalesData.season_id == season_id,
                SalesData.store_id.in_(active_store_ids),
            )
            .group_by(SalesData.store_id, SKU.category)
        )
    ).all()

    fabric_rows = (
        await db.execute(
            select(
                SalesData.store_id,
                SKU.fabric,
                func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
            )
            .join(SKU, SKU.id == SalesData.sku_id)
            .where(
                SalesData.brand_id == brand_id,
                SalesData.season_id == season_id,
                SalesData.store_id.in_(active_store_ids),
            )
            .group_by(SalesData.store_id, SKU.fabric)
        )
    ).all()

    weekly_rows = (
        await db.execute(
            select(
                SalesData.store_id,
                SalesData.week_start_date,
                func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
            )
            .where(
                SalesData.brand_id == brand_id,
                SalesData.season_id == season_id,
                SalesData.store_id.in_(active_store_ids),
            )
            .group_by(SalesData.store_id, SalesData.week_start_date)
            .order_by(SalesData.store_id, SalesData.week_start_date)
        )
    ).all()

    sample_rows = (
        await db.execute(
            select(
                SalesData.store_id,
                func.count().label("row_count"),
            )
            .where(
                SalesData.brand_id == brand_id,
                SalesData.season_id == season_id,
                SalesData.store_id.in_(active_store_ids),
            )
            .group_by(SalesData.store_id)
        )
    ).all()
    sample_size_map: dict[UUID, int] = {row.store_id: int(row.row_count or 0) for row in sample_rows}

    by_store_category: dict[UUID, dict[str, float]] = defaultdict(dict)
    by_store_fabric: dict[UUID, dict[str, float]] = defaultdict(dict)
    weekly_by_store: dict[UUID, list[float]] = defaultdict(list)
    brand_category_totals: dict[str, float] = defaultdict(float)
    brand_fabric_totals: dict[str, float] = defaultdict(float)

    for store_id, category, units in category_rows:
        if category:
            value = float(units or 0.0)
            key = str(category)
            by_store_category[store_id][key] = value
            brand_category_totals[key] += value

    for store_id, fabric, units in fabric_rows:
        if fabric:
            value = float(units or 0.0)
            key = str(fabric)
            by_store_fabric[store_id][key] = value
            brand_fabric_totals[key] += value

    for store_id, _week_start, units in weekly_rows:
        weekly_by_store[store_id].append(float(units or 0.0))

    brand_category_total = sum(brand_category_totals.values())
    brand_fabric_total = sum(brand_fabric_totals.values())

    existing_rows = (
        await db.execute(
            select(StoreBehaviorProfile)
            .where(
                StoreBehaviorProfile.brand_id == brand_id,
                StoreBehaviorProfile.store_id.in_(active_store_ids),
            )
        )
    ).scalars().all()
    existing_by_store = {row.store_id: row for row in existing_rows}

    now = utcnow()
    upserts = 0
    for store_id in active_store_ids:
        store_sample_size = int(sample_size_map.get(store_id, 0))
        store_category = by_store_category.get(store_id, {})
        store_fabric = by_store_fabric.get(store_id, {})
        store_category_total = sum(store_category.values())
        store_fabric_total = sum(store_fabric.values())

        # Compute but do not persist velocity yet; we keep this for future schema expansion.
        _velocity_archetype = _classify_velocity_archetype(weekly_by_store.get(store_id, []))

        category_affinity: dict[str, float] = {}
        fabric_affinity: dict[str, float] = {}
        if store_sample_size >= 100:
            category_affinity = _calculate_affinity(
                store_dim=store_category,
                store_total=store_category_total,
                brand_dim=brand_category_totals,
                brand_total=brand_category_total,
            )
            fabric_affinity = _calculate_affinity(
                store_dim=store_fabric,
                store_total=store_fabric_total,
                brand_dim=brand_fabric_totals,
                brand_total=brand_fabric_total,
            )

        top_category = max(category_affinity, key=category_affinity.get) if category_affinity else None
        top_fabric = max(fabric_affinity, key=fabric_affinity.get) if fabric_affinity else None

        row = existing_by_store.get(store_id)
        if row is None:
            row = StoreBehaviorProfile(
                brand_id=brand_id,
                store_id=store_id,
                created_at=now,
                updated_at=now,
            )
            db.add(row)

        row.primary_category_affinity = top_category
        row.primary_fabric_affinity = top_fabric
        row.category_affinity_score = category_affinity.get(top_category) if top_category else None
        row.fabric_affinity_score = fabric_affinity.get(top_fabric) if top_fabric else None
        row.sample_size = store_sample_size
        row.profile_window_weeks = max(len(weekly_by_store.get(store_id, [])), 1)
        row.updated_at = now
        upserts += 1

    await db.flush()
    return upserts
