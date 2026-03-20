from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SalesData, SKU, StoreBehaviorProfile
from app.utils.date_utils import utcnow


@dataclass
class ProfileSignal:
    category_affinity: str | None
    fabric_affinity: str | None
    category_affinity_score: float | None
    fabric_affinity_score: float | None
    sample_size: int


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
