from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Mapping
from uuid import UUID

from sqlalchemy import distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BrandSettings, SKU, SalesData, Season, Store, StoreProductGrade
from app.services.allocation.constants import (
    DEFAULT_GRADE,
    DEFAULT_MIN_PRESENTATION_QTY,
    DEFAULT_SEASON_WEEKS_REMAINING,
    GRADE_MULTIPLIERS,
)


@dataclass(frozen=True)
class DemandSignal:
    demand: int
    weekly_ros: float
    ros_source: str
    grade: str
    grade_multiplier: float
    is_corrected: bool = False
    stockout_week: int | None = None
    lost_sales_estimate: float | None = None
    data_sample_size: int = 0
    cluster_store_count: int = 0
    matched_style_code: str | None = None
    similarity_score: float | None = None


@dataclass
class TrueDemandResult:
    """Refined demand signal with full context for Phase 2."""
    weekly_ros: float
    source: str
    is_corrected: bool = False
    stockout_week: int | None = None
    lost_sales_estimate: float | None = None
    data_sample_size: int = 0
    cluster_store_count: int = 0
    raw_weekly_ros: float = 0.0


def _infer_stockout_week(sales_by_week: list[int]) -> int | None:
    n = len(sales_by_week)
    if n < 6:
        return None

    for idx in range(2, n - 2):
        if all(sales_by_week[j] == 0 for j in range(idx, min(idx + 3, n))):
            preceding = sales_by_week[max(0, idx - 3) : idx]
            if preceding and sum(preceding) > 0 and preceding[-1] > 0:
                return idx - 1
    return None


async def _calculate_stockout_correction(
    db: AsyncSession,
    brand_id: UUID,
    store_id: UUID,
    category: str,
    season_id: UUID | None,
    preloaded_rows: list[tuple[date, int, bool | None]] | None = None,
) -> tuple[float | None, int | None, float | None, int]:
    if preloaded_rows is not None:
        rows = preloaded_rows
    else:
        date_range = await _season_date_range(db, brand_id, season_id)
        if date_range is None:
            return None, None, None, 0

        start_date, end_date = date_range
        rows = (
            await db.execute(
                select(
                    SalesData.week_start_date,
                    func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
                    func.bool_and(SalesData.was_in_stock).label("all_in_stock"),
                )
                .join(SKU, SKU.id == SalesData.sku_id)
                .where(
                    SalesData.brand_id == brand_id,
                    SalesData.store_id == store_id,
                    SKU.category == category,
                    SalesData.week_start_date >= start_date,
                    SalesData.week_start_date <= end_date,
                )
                .group_by(SalesData.week_start_date)
                .order_by(SalesData.week_start_date)
            )
        ).all()

    if not rows:
        return None, None, None, 0

    sales_by_week = [int(row[1] if isinstance(row, tuple) else row.units or 0) for row in rows]
    total_weeks = len(sales_by_week)
    total_sold = float(sum(sales_by_week))

    stockout_week: int | None = None
    if all((row[2] if isinstance(row, tuple) else row.all_in_stock) is not None for row in rows):
        for idx, row in enumerate(rows):
            in_stock = row[2] if isinstance(row, tuple) else row.all_in_stock
            if bool(in_stock):
                continue
            if idx < total_weeks - 1:
                tail = sales_by_week[idx + 1 :]
                if sum(tail) == 0:
                    stockout_week = idx
                    break

    if stockout_week is None:
        stockout_week = _infer_stockout_week(sales_by_week)

    if stockout_week is None or stockout_week <= 1:
        return (total_sold / total_weeks) if total_weeks else None, None, None, total_weeks

    weeks_with_stock = stockout_week + 1
    sales_with_stock = float(sum(sales_by_week[:weeks_with_stock]))
    if weeks_with_stock <= 0 or sales_with_stock <= 0:
        return (total_sold / total_weeks) if total_weeks else None, None, None, total_weeks

    ros_selling_period = sales_with_stock / weeks_with_stock
    estimated_full_season = ros_selling_period * total_weeks
    corrected_ros = estimated_full_season / total_weeks if total_weeks else None
    lost_sales_estimate = max(0.0, estimated_full_season - total_sold)
    return corrected_ros, stockout_week, round(lost_sales_estimate, 1), total_weeks


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


async def preload_stockout_signals(
    db: AsyncSession,
    brand_id: UUID,
    season_id: UUID | None,
) -> dict[tuple[UUID, str], list[tuple[date, int, bool | None]]]:
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return {}

    start_date, end_date = date_range
    rows = await db.execute(
        select(
            SalesData.store_id,
            SKU.category,
            SalesData.week_start_date,
            func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
            func.bool_and(SalesData.was_in_stock).label("all_in_stock"),
        )
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
        )
        .group_by(SalesData.store_id, SKU.category, SalesData.week_start_date)
        .order_by(SalesData.store_id, SKU.category, SalesData.week_start_date)
    )

    signal_map: dict[tuple[UUID, str], list[tuple[date, int, bool | None]]] = {}
    for store_id, category, week_start_date, units, all_in_stock in rows.all():
        if category is None:
            continue
        signal_map.setdefault((store_id, category), []).append(
            (week_start_date, int(units or 0), all_in_stock)
        )
    return signal_map


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
    preloaded_stockout_signals: Mapping[tuple[UUID, str], list[tuple[date, int, bool | None]]] | None = None,
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

    sample_size = 0
    is_corrected = False
    stockout_week: int | None = None
    lost_sales_estimate: float | None = None
    cluster_store_count = 0

    if store_ros is not None and float(store_ros) > 0:
        source = "store_historical"
        base_ros = float(store_ros)
        corrected_ros, stockout_week, lost_sales_estimate, sample_size = await _calculate_stockout_correction(
            db=db,
            brand_id=brand_id,
            store_id=store.id,
            category=category,
            season_id=previous_season_id,
            preloaded_rows=(preloaded_stockout_signals or {}).get((store.id, category)),
        )
        if corrected_ros is not None and corrected_ros > base_ros:
            base_ros = corrected_ros
            is_corrected = True
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
                data_sample_size=0,
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
        is_corrected=is_corrected,
        stockout_week=stockout_week,
        lost_sales_estimate=lost_sales_estimate,
        data_sample_size=sample_size,
        cluster_store_count=cluster_store_count,
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


def build_allocation_reasoning(
    store_id: str,
    sku_id: str,
    grade: str,
    demand_result: TrueDemandResult,
    cover_target_weeks: int,
    raw_demand_units: int,
    final_qty: int,
    available_qty: int,
    size_result: dict,
    season_weeks_remaining: int,
    grade_multiplier: float,
    story_concentration_note: str | None = None,
    excluded_by_capacity: bool = False,
    exclusion_reason: str | None = None,
) -> dict:
    """Build complete reasoning payload for an allocation line."""
    from app.services.allocation.constants import GRADE_MULTIPLIERS

    weekly_ros = demand_result.weekly_ros
    scale_factor = final_qty / raw_demand_units if raw_demand_units > 0 else 1.0
    weeks_at_final = (final_qty / weekly_ros) if weekly_ros > 0 else 0.0

    return {
        # DEMAND
        "weekly_ros": round(weekly_ros, 3),
        "raw_weekly_ros": round(demand_result.raw_weekly_ros, 3),
        "ros_source": demand_result.source,
        "is_stockout_corrected": demand_result.is_corrected,
        "stockout_week": demand_result.stockout_week,
        "lost_sales_estimate": demand_result.lost_sales_estimate,
        "data_sample_size": demand_result.data_sample_size,
        "cluster_store_count": demand_result.cluster_store_count,
        # PROJECTION
        "cover_target_weeks": cover_target_weeks,
        "weeks_cover_at_recommended": round(weeks_at_final, 1),
        "weeks_cover_minus_25pct": round(weeks_at_final * 0.75, 1),
        "weeks_cover_plus_25pct": round(weeks_at_final * 1.25, 1),
        "season_weeks_remaining": season_weeks_remaining,
        "raw_demand_units": raw_demand_units,
        "scale_factor": round(scale_factor, 4),
        # STORE ADJUSTMENTS
        "store_grade": grade,
        "grade_multiplier": grade_multiplier,
        "category_affinity": None,
        "fabric_affinity": None,
        "affinity_adjustment_units": None,
        # STORY CONCENTRATION
        "cannibalization_factor": None,
        "cannibalization_reason": story_concentration_note,
        "colourways_in_story_at_store": None,
        # CAPACITY EXCLUSION
        "excluded_by_capacity": excluded_by_capacity,
        "exclusion_reason": exclusion_reason,
        # SIZE SPLIT
        "size_split": size_result.get("size_split", {}),
        "size_distribution_source": size_result.get("source", "store_historical"),
        "size_distribution_season": size_result.get("season_code"),
        # NARRATIVES (simplified for Phase 1)
        "narrative_demand": (
            f"Weekly ROS: {demand_result.weekly_ros:.1f} units/week "
            f"({demand_result.source}, {demand_result.data_sample_size}w history)"
            + (f". Stockout-corrected from {demand_result.raw_weekly_ros:.1f} in week {demand_result.stockout_week}." 
               if demand_result.is_corrected else ".")
        ),
        "narrative_adjustments": f"Grade {grade} multiplier: {grade_multiplier:.2f}x",
        "narrative_cap": (
            f"Scaled {raw_demand_units} → {final_qty} (factor {scale_factor:.2f}). "
            if scale_factor < 0.99
            else "Full demand met within warehouse availability."
        ),
        "confidence_basis": (
            f"High confidence ({demand_result.data_sample_size}w history)"
            if demand_result.data_sample_size >= 12
            else f"Moderate confidence ({demand_result.data_sample_size}w history)"
            if demand_result.data_sample_size >= 6
            else f"Low confidence ({demand_result.data_sample_size}w history)"
        ),
        # PHASE 2 PLACEHOLDERS
        "style_dna_match": None,
    }


async def _get_cluster_avg_ros(
    db: AsyncSession,
    brand_id: UUID,
    cluster_id: UUID,
    sku_id: UUID,
    season_id: UUID | None,
) -> TrueDemandResult:
    """
    Get average ROS for a SKU across all active stores in a cluster.
    """
    if cluster_id is None:
        return TrueDemandResult(weekly_ros=0.0, source="cluster_average")
    
    result = await db.execute(
        select(
            func.avg(
                func.sum(SalesData.units_sold) /
                func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            ).label("avg_ros"),
            func.count(distinct(Store.id)).label("store_count"),
        )
        .select_from(Store)
        .join(SalesData, SalesData.store_id == Store.id)
        .where(
            Store.cluster_id == cluster_id,
            Store.brand_id == brand_id,
            Store.is_active == True,
            SalesData.sku_id == sku_id,
            SalesData.brand_id == brand_id,
        )
        .group_by(Store.id)
    )
    rows = result.all()
    if rows and len(rows) > 0:
        avg_values = [float(row[0]) for row in rows if row[0] is not None]
        if avg_values:
            cluster_avg = sum(avg_values) / len(avg_values)
            return TrueDemandResult(
                weekly_ros=cluster_avg,
                source="cluster_average",
                cluster_store_count=len(rows),
                raw_weekly_ros=cluster_avg,
            )
    return TrueDemandResult(weekly_ros=0.0, source="cluster_average")


async def _get_grade_avg_ros(
    db: AsyncSession,
    brand_id: UUID,
    grade: str,
    sku_id: UUID,
    season_id: UUID | None,
) -> TrueDemandResult:
    """
    Average ROS across all stores of this grade with history for this SKU.
    """
    normalized_grade = _normalize_grade(grade)
    result = await db.execute(
        text("""
            SELECT AVG(store_ros) AS avg_ros
            FROM (
                SELECT 
                    sd.store_id,
                    SUM(sd.units_sold)::float / NULLIF(COUNT(DISTINCT sd.week_start_date), 0) AS store_ros
                FROM sales_data sd
                JOIN store_product_grades g 
                    ON g.store_id = sd.store_id 
                    AND g.brand_id = sd.brand_id
                WHERE sd.sku_id = :sku_id
                  AND sd.brand_id = :brand_id
                  AND g.grade = :grade
                GROUP BY sd.store_id
            ) ros_by_store
            WHERE store_ros > 0
        """),
        {"brand_id": str(brand_id), "sku_id": str(sku_id), "grade": normalized_grade}
    )
    row = result.first()
    if row and row.avg_ros:
        return TrueDemandResult(
            weekly_ros=float(row.avg_ros),
            source="grade_average",
            raw_weekly_ros=float(row.avg_ros),
        )
    return TrueDemandResult(weekly_ros=0.0, source="grade_average")


async def calculate_demand_with_fallback(
    db: AsyncSession,
    brand_id: UUID,
    store_id: UUID,
    sku_id: UUID,
    season_id: UUID,
    store_grade: str,
    cluster_id: UUID | None,
    preloaded_stockout_signals: dict | None = None,
) -> TrueDemandResult:
    """
    Full demand fallback chain:
    1. Store historical (with stockout correction)
    2. Cluster average ROS for this SKU
    3. Grade average ROS for this category
    4. Minimum presentation (weekly_ros = 0, source = 'minimum_presentation')
    """
    from app.models import SKU as SKUModel
    
    # Get SKU to access category
    sku = await db.get(SKUModel, sku_id)
    if sku is None:
        return TrueDemandResult(weekly_ros=0.0, source="error")
    
    category = sku.category
    
    # Try store-level ROS
    store_ros = await _load_store_weekly_ros_from_db(
        db=db,
        brand_id=brand_id,
        store_id=store_id,
        product_category=category,
        season_id=season_id,
    )
    
    if store_ros is not None and float(store_ros) > 0:
        # Apply stockout correction if available
        corrected_ros, stockout_week, lost_sales, sample_size = await _calculate_stockout_correction(
            db=db,
            brand_id=brand_id,
            store_id=store_id,
            category=category,
            season_id=season_id,
            preloaded_rows=(preloaded_stockout_signals or {}).get((store_id, category)),
        )
        
        if corrected_ros is not None and corrected_ros > float(store_ros):
            return TrueDemandResult(
                weekly_ros=corrected_ros,
                raw_weekly_ros=float(store_ros),
                source="store_historical",
                is_corrected=True,
                stockout_week=stockout_week,
                lost_sales_estimate=lost_sales,
                data_sample_size=sample_size,
            )
        return TrueDemandResult(
            weekly_ros=float(store_ros),
            raw_weekly_ros=float(store_ros),
            source="store_historical",
            is_corrected=False,
            data_sample_size=sample_size,
        )
    
    # Try cluster-level ROS
    if cluster_id:
        cluster_result = await _get_cluster_avg_ros(db, brand_id, cluster_id, sku_id, season_id)
        if cluster_result.weekly_ros > 0:
            return cluster_result
    
    # Try grade-level ROS
    grade_result = await _get_grade_avg_ros(db, brand_id, store_grade, sku_id, season_id)
    if grade_result.weekly_ros > 0:
        return grade_result
    
    # Fallback to minimum presentation
    return TrueDemandResult(
        weekly_ros=0.0,
        source="minimum_presentation",
        raw_weekly_ros=0.0,
    )
