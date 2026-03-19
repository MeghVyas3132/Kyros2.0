from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Mapping
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BrandSettings, SKU, SalesData, Season, Store, StoreProductGrade

GRADE_MULTIPLIERS: dict[str, float] = {
    "A+": 1.25,
    "A": 1.00,
    "B": 0.75,
    "C": 0.50,
}
DEFAULT_GRADE = "C"
DEFAULT_MIN_PRESENTATION_QTY = 2
DEFAULT_SEASON_WEEKS_REMAINING = 8


@dataclass(frozen=True)
class DemandSignal:
    demand: int
    weekly_ros: float
    ros_source: str
    grade: str
    grade_multiplier: float


async def load_sales_history(
    db: AsyncSession,
    brand_id: UUID,
    season_id: UUID | None,
) -> dict[tuple[UUID, str], float]:
    """Return store x category weekly ROS for the selected season."""
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return {}

    start_date, end_date = date_range
    rows = await db.execute(
        select(
            SalesData.store_id,
            SKU.category,
            (
                func.coalesce(func.sum(SalesData.units_sold), 0)
                / func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            ).label("weekly_ros"),
        )
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
        )
        .group_by(SalesData.store_id, SKU.category)
    )

    result: dict[tuple[UUID, str], float] = {}
    for store_id, category, weekly_ros in rows.all():
        if category is None:
            continue
        value = float(weekly_ros or 0.0)
        if value <= 0:
            continue
        result[(store_id, category)] = value
    return result


async def load_grade_map(db: AsyncSession, brand_id: UUID) -> dict[tuple[UUID, str], str]:
    """Return canonical product-category grade for each store."""
    rows = await db.execute(
        select(
            StoreProductGrade.store_id,
            StoreProductGrade.product_category,
            StoreProductGrade.grade,
        ).where(StoreProductGrade.brand_id == brand_id)
    )

    result: dict[tuple[UUID, str], str] = {}
    for store_id, product_category, grade in rows.all():
        if product_category is None:
            continue
        key = (store_id, product_category)
        current = result.get(key)
        if current is None or _grade_rank(grade) > _grade_rank(current):
            result[key] = _normalize_grade(grade)
    return result


async def load_grade_ros_averages(
    db: AsyncSession,
    brand_id: UUID,
    season_id: UUID | None,
) -> dict[tuple[str, str], float]:
    """Return grade x category average weekly ROS."""
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return {}

    start_date, end_date = date_range

    store_ros_subquery = (
        select(
            SalesData.store_id.label("store_id"),
            SKU.category.label("category"),
            (
                func.coalesce(func.sum(SalesData.units_sold), 0)
                / func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            ).label("store_weekly_ros"),
        )
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
        )
        .group_by(SalesData.store_id, SKU.category)
        .subquery()
    )

    rows = await db.execute(
        select(
            StoreProductGrade.grade,
            StoreProductGrade.product_category,
            func.avg(store_ros_subquery.c.store_weekly_ros).label("grade_avg_ros"),
        )
        .join(
            store_ros_subquery,
            (store_ros_subquery.c.store_id == StoreProductGrade.store_id)
            & (store_ros_subquery.c.category == StoreProductGrade.product_category),
        )
        .where(StoreProductGrade.brand_id == brand_id)
        .group_by(StoreProductGrade.grade, StoreProductGrade.product_category)
    )

    result: dict[tuple[str, str], float] = {}
    for grade, product_category, avg_ros in rows.all():
        if product_category is None:
            continue
        value = float(avg_ros or 0.0)
        if value <= 0:
            continue
        result[(_normalize_grade(grade), product_category)] = value
    return result


async def calculate_store_demand(
    db: AsyncSession,
    brand_id: UUID,
    sku: SKU,
    store: Store,
    season_weeks_remaining: int,
    fallback_grade: str,
    *,
    sales_by_store_category: Mapping[tuple[UUID, str], float] | None = None,
    grade_ros_averages: Mapping[tuple[str, str], float] | None = None,
    min_presentation_qty: int | None = None,
    previous_season_id: UUID | None = None,
) -> int:
    signal = await calculate_store_demand_details(
        db=db,
        brand_id=brand_id,
        sku=sku,
        store=store,
        season_weeks_remaining=season_weeks_remaining,
        fallback_grade=fallback_grade,
        sales_by_store_category=sales_by_store_category,
        grade_ros_averages=grade_ros_averages,
        min_presentation_qty=min_presentation_qty,
        previous_season_id=previous_season_id,
    )
    return signal.demand


async def calculate_store_demand_details(
    db: AsyncSession,
    brand_id: UUID,
    sku: SKU,
    store: Store,
    season_weeks_remaining: int,
    fallback_grade: str,
    *,
    sales_by_store_category: Mapping[tuple[UUID, str], float] | None = None,
    grade_ros_averages: Mapping[tuple[str, str], float] | None = None,
    min_presentation_qty: int | None = None,
    previous_season_id: UUID | None = None,
) -> DemandSignal:
    category = sku.category
    grade = _normalize_grade(fallback_grade)
    min_qty = min_presentation_qty if min_presentation_qty is not None else await get_min_presentation_qty(db, brand_id)
    weeks_remaining = max(int(season_weeks_remaining or DEFAULT_SEASON_WEEKS_REMAINING), 1)

    store_ros = None
    if sales_by_store_category is not None:
        store_ros = sales_by_store_category.get((store.id, category))
    if store_ros is None:
        store_ros = await _load_store_weekly_ros_from_db(
            db=db,
            brand_id=brand_id,
            store_id=store.id,
            product_category=category,
            season_id=previous_season_id,
        )

    if store_ros is not None and float(store_ros) > 0:
        source = "store_historical"
        base_ros = float(store_ros)
    else:
        grade_ros = None
        if grade_ros_averages is not None:
            grade_ros = grade_ros_averages.get((grade, category))
        if grade_ros is None:
            grade_ros = await _load_grade_weekly_ros_from_db(
                db=db,
                brand_id=brand_id,
                product_category=category,
                grade=grade,
                season_id=previous_season_id,
            )

        if grade_ros is not None and float(grade_ros) > 0:
            source = "grade_average"
            base_ros = float(grade_ros)
        else:
            return DemandSignal(
                demand=int(min_qty),
                weekly_ros=0.0,
                ros_source="minimum_presentation",
                grade=grade,
                grade_multiplier=GRADE_MULTIPLIERS.get(grade, 1.00),
            )

    multiplier = GRADE_MULTIPLIERS.get(grade, 1.00)
    adjusted_ros = base_ros * multiplier
    raw_demand = round(adjusted_ros * weeks_remaining)
    raw_demand = int(max(raw_demand, min_qty))

    return DemandSignal(
        demand=raw_demand,
        weekly_ros=base_ros,
        ros_source=source,
        grade=grade,
        grade_multiplier=multiplier,
    )


async def get_min_presentation_qty(db: AsyncSession, brand_id: UUID) -> int:
    config = await db.scalar(select(BrandSettings.config).where(BrandSettings.brand_id == brand_id))
    if isinstance(config, dict):
        value = config.get("min_presentation_qty")
        if isinstance(value, int) and value > 0:
            return value
    return DEFAULT_MIN_PRESENTATION_QTY


async def get_season_weeks_remaining(
    db: AsyncSession,
    brand_id: UUID,
    current_season_id: UUID | None,
) -> int:
    config = await db.scalar(select(BrandSettings.config).where(BrandSettings.brand_id == brand_id))

    dynamic_weeks = await _dynamic_weeks_remaining(db, brand_id, current_season_id)
    if dynamic_weeks is not None:
        return dynamic_weeks

    if isinstance(config, dict):
        configured = config.get("season_weeks_remaining")
        if isinstance(configured, int) and configured > 0:
            return configured

    return DEFAULT_SEASON_WEEKS_REMAINING


async def get_previous_season_id(
    db: AsyncSession,
    brand_id: UUID,
    current_season_id: UUID | None,
) -> UUID | None:
    current_start = None
    if current_season_id is not None:
        current_start = await db.scalar(
            select(Season.start_date).where(Season.id == current_season_id, Season.brand_id == brand_id)
        )

    if current_start is not None:
        previous = await db.scalar(
            select(Season.id)
            .where(Season.brand_id == brand_id, Season.start_date < current_start)
            .order_by(Season.start_date.desc())
            .limit(1)
        )
        if previous is not None:
            return previous

    seasons = (
        await db.execute(
            select(Season.id)
            .where(Season.brand_id == brand_id)
            .order_by(Season.start_date.desc())
            .limit(2)
        )
    ).scalars().all()
    if len(seasons) >= 2:
        return seasons[1]
    return seasons[0] if seasons else None


async def _dynamic_weeks_remaining(
    db: AsyncSession,
    brand_id: UUID,
    current_season_id: UUID | None,
) -> int | None:
    season: Season | None = None
    if current_season_id is not None:
        season = await db.scalar(
            select(Season).where(Season.id == current_season_id, Season.brand_id == brand_id)
        )

    if season is None:
        today = date.today()
        season = await db.scalar(
            select(Season)
            .where(
                Season.brand_id == brand_id,
                Season.start_date <= today,
                Season.end_date >= today,
            )
            .order_by(Season.start_date.desc())
        )

    if season is None:
        return None

    today = date.today()
    if season.end_date <= today:
        return 1

    days_remaining = max((season.end_date - today).days, 1)
    return max(1, ceil(days_remaining / 7))


async def _season_date_range(
    db: AsyncSession,
    brand_id: UUID,
    season_id: UUID | None,
) -> tuple[date, date] | None:
    if season_id is None:
        return None

    row = await db.execute(
        select(Season.start_date, Season.end_date).where(
            Season.id == season_id,
            Season.brand_id == brand_id,
        )
    )
    result = row.one_or_none()
    if result is None:
        return None
    return result[0], result[1]


async def _load_store_weekly_ros_from_db(
    db: AsyncSession,
    brand_id: UUID,
    store_id: UUID,
    product_category: str,
    season_id: UUID | None,
) -> float | None:
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return None

    start_date, end_date = date_range
    row = await db.execute(
        select(
            (
                func.coalesce(func.sum(SalesData.units_sold), 0)
                / func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            ).label("weekly_ros"),
        )
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SalesData.store_id == store_id,
            SKU.category == product_category,
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
        )
    )
    value = row.scalar_one_or_none()
    if value is None:
        return None
    weekly_ros = float(value or 0.0)
    return weekly_ros if weekly_ros > 0 else None


async def _load_grade_weekly_ros_from_db(
    db: AsyncSession,
    brand_id: UUID,
    product_category: str,
    grade: str,
    season_id: UUID | None,
) -> float | None:
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return None

    start_date, end_date = date_range
    store_ros_subquery = (
        select(
            SalesData.store_id.label("store_id"),
            (
                func.coalesce(func.sum(SalesData.units_sold), 0)
                / func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            ).label("store_weekly_ros"),
        )
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SKU.category == product_category,
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
        )
        .group_by(SalesData.store_id)
        .subquery()
    )

    row = await db.execute(
        select(func.avg(store_ros_subquery.c.store_weekly_ros))
        .join(
            StoreProductGrade,
            (StoreProductGrade.store_id == store_ros_subquery.c.store_id)
            & (StoreProductGrade.product_category == product_category)
            & (StoreProductGrade.brand_id == brand_id),
        )
        .where(StoreProductGrade.grade == grade)
    )
    value = row.scalar_one_or_none()
    if value is None:
        return None
    avg_ros = float(value or 0.0)
    return avg_ros if avg_ros > 0 else None


def _normalize_grade(grade: str | None) -> str:
    cleaned = (grade or DEFAULT_GRADE).strip().upper()
    if cleaned in {"A+", "A", "B", "C"}:
        return cleaned
    return DEFAULT_GRADE


def _grade_rank(grade: str | None) -> int:
    order = {"A+": 4, "A": 3, "B": 2, "C": 1}
    return order.get(_normalize_grade(grade), 1)
