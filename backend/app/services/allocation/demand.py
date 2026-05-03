from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Literal, Mapping, MutableMapping
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


DemandRosSource = Literal[
    "store_historical",
    "cluster_average",
    "grade_average",
    "style_dna_analogue",
    "minimum_presentation",
]

StyleDnaCacheKey = tuple[UUID, str, str, str, str, str, str, str, UUID | None]
StyleDnaProxy = tuple[float, str, float, int]


@dataclass(frozen=True)
class DemandSignal:
    demand: int
    weekly_ros: float
    ros_source: DemandRosSource
    grade: str
    grade_multiplier: float
    is_corrected: bool = False
    stockout_week: int | None = None
    lost_sales_estimate: float | None = None
    data_sample_size: int = 0
    cluster_store_count: int = 0
    matched_style_code: str | None = None
    similarity_score: float | None = None
    # Style-analogue audit trail. Carries the full top-K match list
    # (not just the leader) so the UI can show the planner exactly which
    # prior styles drove the inference.
    analogue_match_meta: dict | None = None


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
) -> dict[tuple[UUID, UUID], float]:
    """Return store x SKU weekly ROS for the selected season."""
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return {}

    start_date, end_date = date_range
    rows = await db.execute(
        select(
            SalesData.store_id,
            SalesData.sku_id,
            func.sum(SalesData.units_sold).label("total_sold"),
            func.count(distinct(SalesData.week_start_date)).label("weeks_with_data"),
        )
        .where(
            SalesData.brand_id == brand_id,
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
        )
        .group_by(SalesData.store_id, SalesData.sku_id)
    )

    result: dict[tuple[UUID, UUID], float] = {}
    for store_id, sku_id, total_sold, weeks_with_data in rows.all():
        if weeks_with_data is None or weeks_with_data == 0:
            continue
        weekly_ros = float(total_sold or 0) / float(weeks_with_data)
        if weekly_ros <= 0:
            continue
        result[(store_id, sku_id)] = weekly_ros
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
        signal_map.setdefault((store_id, _normalize_category(category)), []).append(
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
        key = (store_id, _normalize_category(product_category))
        current = result.get(key)
        if current is None or _grade_rank(grade) > _grade_rank(current):
            result[key] = _normalize_grade(grade)
    return result


async def load_grade_ros_averages(
    db: AsyncSession,
    brand_id: UUID,
    season_id: UUID | None,
) -> dict[tuple[str, UUID], float]:
    """Return grade x SKU average weekly ROS."""
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return {}

    start_date, end_date = date_range

    # Subquery: Calculate weekly ROS per store × SKU
    store_ros_subquery = (
        select(
            SalesData.store_id.label("store_id"),
            SalesData.sku_id.label("sku_id"),
            SKU.category.label("category"),
            (
                func.sum(SalesData.units_sold)
                / func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            ).label("store_weekly_ros"),
        )
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
        )
        .group_by(SalesData.store_id, SalesData.sku_id, SKU.category)
        .subquery()
    )

    # Join with store grades and average by grade × SKU
    rows = await db.execute(
        select(
            StoreProductGrade.grade,
            store_ros_subquery.c.sku_id,
            func.avg(store_ros_subquery.c.store_weekly_ros).label("grade_avg_ros"),
        )
        .join(
            store_ros_subquery,
            (store_ros_subquery.c.store_id == StoreProductGrade.store_id)
            & (
                func.lower(func.trim(store_ros_subquery.c.category))
                == func.lower(func.trim(StoreProductGrade.product_category))
            ),
        )
        .where(StoreProductGrade.brand_id == brand_id)
        .group_by(StoreProductGrade.grade, store_ros_subquery.c.sku_id)
    )

    result: dict[tuple[str, UUID], float] = {}
    for grade, sku_id, avg_ros in rows.all():
        if sku_id is None:
            continue
        value = float(avg_ros or 0.0)
        if value <= 0:
            continue
        result[(_normalize_grade(grade), sku_id)] = value
    return result


async def load_cluster_ros_averages(
    db: AsyncSession,
    brand_id: UUID,
    season_id: UUID | None,
) -> dict[tuple[UUID, UUID], float]:
    """Return cluster x SKU average weekly ROS (average of store-level ROS)."""
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return {}

    start_date, end_date = date_range
    store_cluster_ros_subquery = (
        select(
            Store.cluster_id.label("cluster_id"),
            SalesData.store_id.label("store_id"),
            SalesData.sku_id.label("sku_id"),
            (
                func.sum(SalesData.units_sold)
                / func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            ).label("store_weekly_ros"),
        )
        .join(Store, Store.id == SalesData.store_id)
        .where(
            SalesData.brand_id == brand_id,
            Store.brand_id == brand_id,
            Store.is_active.is_(True),
            Store.cluster_id.is_not(None),
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
        )
        .group_by(Store.cluster_id, SalesData.store_id, SalesData.sku_id)
        .subquery()
    )

    rows = await db.execute(
        select(
            store_cluster_ros_subquery.c.cluster_id,
            store_cluster_ros_subquery.c.sku_id,
            func.avg(store_cluster_ros_subquery.c.store_weekly_ros).label("cluster_avg_ros"),
        ).group_by(
            store_cluster_ros_subquery.c.cluster_id,
            store_cluster_ros_subquery.c.sku_id,
        )
    )

    result: dict[tuple[UUID, UUID], float] = {}
    for cluster_id, sku_id, cluster_avg_ros in rows.all():
        if cluster_id is None or sku_id is None:
            continue
        value = float(cluster_avg_ros or 0.0)
        if value <= 0:
            continue
        result[(cluster_id, sku_id)] = value
    return result


async def calculate_store_demand(
    db: AsyncSession,
    brand_id: UUID,
    sku: SKU,
    store: Store,
    season_weeks_remaining: int,
    fallback_grade: str,
    *,
    sales_by_store_category: Mapping[tuple[UUID, UUID], float] | None = None,
    grade_ros_averages: Mapping[tuple[str, UUID], float] | None = None,
    cluster_ros_averages: Mapping[tuple[UUID, UUID], float] | None = None,
    min_presentation_qty: int | None = None,
    previous_season_id: UUID | None = None,
    style_dna_cache: MutableMapping[StyleDnaCacheKey, StyleDnaProxy | None] | None = None,
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
        cluster_ros_averages=cluster_ros_averages,
        min_presentation_qty=min_presentation_qty,
        previous_season_id=previous_season_id,
        style_dna_cache=style_dna_cache,
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
    sales_by_store_category: Mapping[tuple[UUID, UUID], float] | None = None,
    grade_ros_averages: Mapping[tuple[str, UUID], float] | None = None,
    cluster_ros_averages: Mapping[tuple[UUID, UUID], float] | None = None,
    min_presentation_qty: int | None = None,
    previous_season_id: UUID | None = None,
    preloaded_stockout_signals: Mapping[tuple[UUID, str], list[tuple[date, int, bool | None]]] | None = None,
    style_dna_cache: MutableMapping[StyleDnaCacheKey, StyleDnaProxy | None] | None = None,
    category_bridge: object | None = None,
    style_analogue: object | None = None,
) -> DemandSignal:
    """
    Calculate demand for a store × SKU combination using four-tier fallback:
    1. Store-specific historical ROS for this SKU (stockout-corrected)
    2. Cluster average ROS for this specific SKU
    3. Grade-level average ROS for this SKU
    4. Style DNA matching (if available)
    5. Minimum presentation quantity
    """
    category = sku.category
    normalized_category = _normalize_category(category)
    grade = _normalize_grade(fallback_grade)
    min_qty = min_presentation_qty if min_presentation_qty is not None else await get_min_presentation_qty(db, brand_id)
    weeks_remaining = max(int(season_weeks_remaining or DEFAULT_SEASON_WEEKS_REMAINING), 1)

    # TIER 1: Try store-specific ROS for this SKU
    store_ros = None
    if sales_by_store_category is not None:
        store_ros = sales_by_store_category.get((store.id, sku.id))
    
    sample_size = 0
    is_corrected = False
    stockout_week: int | None = None
    lost_sales_estimate: float | None = None
    cluster_store_count = 0

    if store_ros is not None and float(store_ros) > 0:
        source = "store_historical"
        base_ros = float(store_ros)
        # Note: Stockout correction is category-level, kept for consistency
        pre_rows = None
        if preloaded_stockout_signals is not None:
            pre_rows = preloaded_stockout_signals.get((store.id, normalized_category), [])

        corrected_ros, stockout_week, lost_sales_estimate, sample_size = await _calculate_stockout_correction(
            db=db,
            brand_id=brand_id,
            store_id=store.id,
            category=category,
            season_id=previous_season_id,
            preloaded_rows=pre_rows,
        )
        if corrected_ros is not None and corrected_ros > base_ros:
            base_ros = corrected_ros
            is_corrected = True
    else:
        # TIER 1.5 (NEW): Style-analogue inference. For a cold-start SKU we
        # ask "which prior-season styles look most like this one?" and
        # borrow their per-store weekly ROS. This restores style-level
        # granularity that the category bridge averages out.
        analogue_hit = None
        if style_analogue is not None:
            try:
                analogue_hit = style_analogue.infer_demand(store.id, sku)
            except Exception:  # noqa: BLE001
                analogue_hit = None
        if analogue_hit is not None and analogue_hit.weekly_ros > 0:
            multiplier = GRADE_MULTIPLIERS.get(grade, 1.00)
            base_ros = float(analogue_hit.weekly_ros)
            raw_demand = round(base_ros * weeks_remaining)
            raw_demand = int(max(raw_demand, min_qty))
            return DemandSignal(
                demand=raw_demand,
                weekly_ros=base_ros,
                ros_source="style_analogue",
                grade=grade,
                grade_multiplier=multiplier,
                is_corrected=False,
                data_sample_size=int(analogue_hit.sample_size_weeks),
                cluster_store_count=len(analogue_hit.matched_style_codes),
                # Identify the TOP analogue for the existing reasoning fields
                # consumed by build_allocation_reasoning. Full match list is
                # surfaced via ai_reasoning by the explainer.
                matched_style_code=(
                    analogue_hit.matched_style_codes[0]
                    if analogue_hit.matched_style_codes
                    else None
                ),
                similarity_score=float(analogue_hit.best_score),
                analogue_match_meta={
                    "matched_style_codes": list(analogue_hit.matched_style_codes),
                    "scores": list(analogue_hit.scores),
                    "best_score": float(analogue_hit.best_score),
                    "confidence_tier": analogue_hit.confidence_tier,
                    "sample_size_weeks": int(analogue_hit.sample_size_weeks),
                    "explanation": analogue_hit.explanation,
                },
            )

        # TIER 2: Try cluster average ROS for this specific SKU
        cluster_ros = None
        if store.cluster_id is not None and cluster_ros_averages is not None:
            cluster_ros = cluster_ros_averages.get((store.cluster_id, sku.id))

        if cluster_ros is not None and float(cluster_ros) > 0:
            source = "cluster_average"
            base_ros = float(cluster_ros)
            sample_size = 0  # cluster-level, no per-store sample
        else:
            # TIER 2.5 (NEW): Category × price-band demand bridge.
            # When the SKU itself has no history (cold-start), borrow the
            # weekly ROS this *store* showed in the same (category, price_band)
            # last season. Far stronger signal than grade_average for a
            # specific store, and the only thing that lets a brand whose
            # SKU codes change between seasons get past minimum_presentation.
            bridge_hit = None
            if category_bridge is not None:
                try:
                    bridge_hit = category_bridge.lookup(
                        store.id, category, getattr(sku, "price_band", None)
                    )
                except Exception:  # noqa: BLE001
                    bridge_hit = None
            if bridge_hit is not None and bridge_hit.weekly_ros > 0:
                source = "category_bridge"
                base_ros = float(bridge_hit.weekly_ros)
                sample_size = int(bridge_hit.units_observed or 0)
                # Falls through to the post-cascade common return path below.
                multiplier = GRADE_MULTIPLIERS.get(grade, 1.00)
                raw_demand = round(base_ros * weeks_remaining)
                raw_demand = int(max(raw_demand, min_qty))
                return DemandSignal(
                    demand=raw_demand,
                    weekly_ros=base_ros,
                    ros_source=source,
                    grade=grade,
                    grade_multiplier=multiplier,
                    is_corrected=False,
                    data_sample_size=sample_size,
                    cluster_store_count=int(bridge_hit.sample_skus or 0),
                )

            # TIER 3: Try grade-level average for this SKU
            grade_ros = None
            if grade_ros_averages is not None:
                grade_ros = grade_ros_averages.get((grade, sku.id))
            
            if grade_ros is not None and float(grade_ros) > 0:
                source = "grade_average"
                base_ros = float(grade_ros)
            else:
                # TIER 4: Style DNA matching
                style_dna_cache_key = _build_style_dna_cache_key(store.id, sku, previous_season_id)
                style_dna: StyleDnaProxy | None
                if style_dna_cache is not None and style_dna_cache_key in style_dna_cache:
                    style_dna = style_dna_cache[style_dna_cache_key]
                else:
                    style_dna = await _load_style_dna_proxy(
                        db=db,
                        brand_id=brand_id,
                        store_id=store.id,
                        sku=sku,
                        season_id=previous_season_id,
                    )
                    if style_dna_cache is not None:
                        style_dna_cache[style_dna_cache_key] = style_dna
                if style_dna is not None:
                    dna_ros, matched_style_code, similarity_score, dna_sample_size = style_dna
                    source = "style_dna_analogue"
                    multiplier = GRADE_MULTIPLIERS.get(grade, 1.00)
                    raw_demand = round(dna_ros * weeks_remaining)
                    raw_demand = int(max(raw_demand, min_qty))
                    return DemandSignal(
                        demand=raw_demand,
                        weekly_ros=float(dna_ros),
                        ros_source=source,
                        grade=grade,
                        grade_multiplier=multiplier,
                        data_sample_size=dna_sample_size,
                        matched_style_code=matched_style_code,
                        similarity_score=similarity_score,
                    )

                # TIER 5: Fallback to minimum presentation
                return DemandSignal(
                    demand=int(min_qty),
                    weekly_ros=0.0,
                    ros_source="minimum_presentation",
                    grade=grade,
                    grade_multiplier=GRADE_MULTIPLIERS.get(grade, 1.00),
                    data_sample_size=0,
                )

    # Grade multiplier is informational only - do not apply to ROS
    # The weekly_ros stored here is the unadjusted base rate
    # Engine applies multiplier during final calculation
    multiplier = GRADE_MULTIPLIERS.get(grade, 1.00)
    raw_demand = round(base_ros * weeks_remaining)
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


def _attribute_match_score(left: str | None, right: str | None, weight: float) -> float:
    if not left or not right:
        return 0.0
    if left.strip().lower() == right.strip().lower():
        return weight
    return 0.0


def _style_similarity_score(sku: SKU, candidate: dict[str, object]) -> float:
    score = 0.35  # Category is fixed by candidate query
    score += _attribute_match_score(sku.fabric, candidate.get("fabric"), 0.20)
    score += _attribute_match_score(sku.price_band, candidate.get("price_band"), 0.15)
    score += _attribute_match_score(sku.colour_family, candidate.get("colour_family"), 0.15)
    score += _attribute_match_score(sku.resolved_risk_level, candidate.get("resolved_risk_level"), 0.10)
    score += _attribute_match_score(sku.sub_category, candidate.get("sub_category"), 0.05)
    return min(score, 1.0)


async def _load_style_dna_proxy(
    db: AsyncSession,
    brand_id: UUID,
    store_id: UUID,
    sku: SKU,
    season_id: UUID | None,
) -> StyleDnaProxy | None:
    date_range = await _season_date_range(db, brand_id, season_id)
    if date_range is None:
        return None

    start_date, end_date = date_range
    rows = await db.execute(
        select(
            SKU.sku_code,
            SKU.fabric,
            SKU.price_band,
            SKU.colour_family,
            SKU.resolved_risk_level,
            SKU.sub_category,
            (
                func.coalesce(func.sum(SalesData.units_sold), 0)
                / func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            ).label("weekly_ros"),
            func.count(distinct(SalesData.week_start_date)).label("weeks_with_data"),
        )
        .join(SKU, SKU.id == SalesData.sku_id)
        .where(
            SalesData.brand_id == brand_id,
            SalesData.store_id == store_id,
            SalesData.week_start_date >= start_date,
            SalesData.week_start_date <= end_date,
            SKU.category == sku.category,
            SKU.style_code != sku.style_code,
        )
        .group_by(
            SKU.sku_code,
            SKU.fabric,
            SKU.price_band,
            SKU.colour_family,
            SKU.resolved_risk_level,
            SKU.sub_category,
        )
        .having(
            (
                func.coalesce(func.sum(SalesData.units_sold), 0)
                / func.nullif(func.count(distinct(SalesData.week_start_date)), 0)
            )
            > 0
        )
    )

    scored: list[dict[str, object]] = []
    for row in rows.all():
        candidate = {
            "sku_code": row.sku_code,
            "fabric": row.fabric,
            "price_band": row.price_band,
            "colour_family": row.colour_family,
            "resolved_risk_level": row.resolved_risk_level,
            "sub_category": row.sub_category,
            "weekly_ros": float(row.weekly_ros or 0.0),
            "weeks_with_data": int(row.weeks_with_data or 0),
        }
        similarity = _style_similarity_score(sku, candidate)
        if similarity >= 0.45 and candidate["weekly_ros"] > 0:
            candidate["similarity"] = similarity
            scored.append(candidate)

    if not scored:
        return None

    top_matches = sorted(scored, key=lambda item: float(item["similarity"]), reverse=True)[:5]
    weight_sum = sum(float(item["similarity"]) for item in top_matches)
    if weight_sum <= 0:
        return None

    weighted_ros = sum(
        float(item["weekly_ros"]) * float(item["similarity"]) for item in top_matches
    ) / weight_sum
    top_match = top_matches[0]
    avg_similarity = sum(float(item["similarity"]) for item in top_matches) / len(top_matches)
    sample_size = sum(int(item["weeks_with_data"]) for item in top_matches)
    return weighted_ros, str(top_match["sku_code"]), round(avg_similarity, 3), sample_size


def _normalize_grade(grade: str | None) -> str:
    cleaned = (grade or DEFAULT_GRADE).strip().upper()
    if cleaned in {"A+", "A", "B", "C"}:
        return cleaned
    return DEFAULT_GRADE


def _normalize_category(category: str | None) -> str:
    return " ".join(str(category or "").strip().lower().split())


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _build_style_dna_cache_key(store_id: UUID, sku: SKU, season_id: UUID | None) -> StyleDnaCacheKey:
    return (
        store_id,
        sku.style_code,
        _normalize_category(sku.category),
        _normalize_text(sku.price_band),
        _normalize_text(sku.colour_family),
        _normalize_text(sku.fabric),
        _normalize_text(sku.resolved_risk_level),
        _normalize_text(sku.sub_category),
        season_id,
    )


def _grade_rank(grade: str | None) -> int:
    order = {"A+": 4, "A": 3, "B": 2, "C": 1}
    return order.get(_normalize_grade(grade), 1)

def calculate_confidence_score(
    ros_source: str,
    data_sample_size: int,
    cap_scale_factor: float,
    is_synthetic: bool,
    is_stockout_corrected: bool,
) -> tuple[str, float]:
    """Returns (tier, numeric_score) where tier is HIGH/MEDIUM/LOW and score is 0-1."""
    
    base_scores = {
        "store_historical": 0.80,
        # Style-analogue: per-store demand inferred from semantically
        # similar prior-season styles. The numeric similarity score is
        # already encoded in ``data_sample_size`` / similarity_score elsewhere;
        # we anchor the base to 0.65 so a strong analogue (≥0.70 score) lands
        # comfortably HIGH, while a marginal analogue lands MEDIUM.
        "style_analogue": 0.65,
        "cluster_average": 0.55,
        # Category × price-band bridge: per-store evidence on the same
        # (category, price_band), aggregated across many SKUs. Strong signal
        # for cold-start; sits between cluster and grade.
        "category_bridge": 0.50,
        "grade_average": 0.40,
        "style_dna_analogue": 0.30,
        "style_dna": 0.30,
        "minimum_presentation": 0.10,
    }
    score = base_scores.get(ros_source, 0.10)
    
    # Adjust for sample size
    if data_sample_size >= 12:
        score += 0.15
    elif data_sample_size >= 6:
        score += 0.05
    elif data_sample_size < 4:
        score -= 0.10
    
    # Penalize synthetic data
    if is_synthetic:
        score *= 0.6
    
    # Penalize heavy capping
    if cap_scale_factor < 0.3:
        score -= 0.10
    
    score = max(0.0, min(1.0, score))
    tier = "HIGH" if score >= 0.65 else "MEDIUM" if score >= 0.35 else "LOW"
    return tier, round(score, 3)




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
    # Phase 2 fields — pass None when not computed yet
    category_affinity: float | None = None,
    fabric_affinity: float | None = None,
    category_affinity_label: str | None = None,
    fabric_affinity_label: str | None = None,
    affinity_adjustment_units: int | None = None,
    affinity_multiplier: float = 1.0,
    cannibalization_factor: float | None = None,
    cannibalization_reason: str | None = None,
    colourways_in_story_at_store: int | None = None,
    style_dna_match: dict | None = None,
    style_analogue_match: dict | None = None,
    excluded_by_capacity: bool = False,
    exclusion_reason: str | None = None,
    # Backward-compat fields used by frontend panel
    store_ros_attribute: str | None = None,
    cluster_avg_ros_attribute: str | None = None,
    ros_vs_cluster_pct: int = 0,
    current_stock_cover_days: float = 0.0,
    display_capacity_available: int | None = None,
    stockout_risk_at_lower_qty: bool = False,
    climate_match: bool = True,
    data_sample_size: int = 0,
    # Deprecated parameter kept for backward compatibility
    story_concentration_note: str | None = None,
    # Phase 2 
    is_synthetic_data: bool = False,
    grade_was_defaulted: bool = False,
    allocation_mode: str = "demand_led",
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
        "stockout_correction_applied": demand_result.is_corrected,  # alias
        "stockout_week": demand_result.stockout_week,
        "lost_sales_estimate": demand_result.lost_sales_estimate,
        "data_sample_size": data_sample_size or demand_result.data_sample_size,
        "cluster_store_count": demand_result.cluster_store_count,
        "allocation_mode": allocation_mode,
        # PROJECTION
        "cover_target_weeks": cover_target_weeks,
        "weeks_cover_at_recommended": round(weeks_at_final, 1),
        "weeks_cover_minus_25pct": round(weeks_at_final * 0.75, 1),
        "weeks_cover_plus_25pct": round(weeks_at_final * 1.25, 1),
        "weeks_cover_minus_25": round(weeks_at_final * 0.75, 1),  # backward compat
        "weeks_cover_plus_25": round(weeks_at_final * 1.25, 1),  # backward compat
        "weeks_cover_at_minus_25pct": round(weeks_at_final * 0.75, 1),  # alias
        "weeks_cover_at_plus_25pct": round(weeks_at_final * 1.25, 1),  # alias
        "season_weeks_remaining": season_weeks_remaining,
        "raw_demand_units": raw_demand_units,
        "scale_factor": round(scale_factor, 4),
        # STORE ADJUSTMENTS
        "store_grade": grade,
        "grade_multiplier": grade_multiplier,
        "category_affinity": category_affinity,
        "fabric_affinity": fabric_affinity,
        "category_affinity_label": category_affinity_label,
        "fabric_affinity_label": fabric_affinity_label,
        "affinity_adjustment_units": affinity_adjustment_units,
        "affinity_multiplier": affinity_multiplier,
        # STORY CONCENTRATION
        "cannibalization_factor": cannibalization_factor,
        "cannibalization_reason": cannibalization_reason or story_concentration_note,
        "colourways_in_story_at_store": colourways_in_story_at_store,
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
            f"({demand_result.source}, {data_sample_size or demand_result.data_sample_size}w history)"
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
            f"High confidence ({data_sample_size or demand_result.data_sample_size}w history)"
            if (data_sample_size or demand_result.data_sample_size) >= 12
            else f"Moderate confidence ({data_sample_size or demand_result.data_sample_size}w history)"
            if (data_sample_size or demand_result.data_sample_size) >= 6
            else f"Low confidence ({data_sample_size or demand_result.data_sample_size}w history)"
        ),
        # PHASE 2 - Confidence and Risk
        "confidence_tier": calculate_confidence_score(
            ros_source=demand_result.source,
            data_sample_size=data_sample_size or demand_result.data_sample_size,
            cap_scale_factor=scale_factor,
            is_synthetic=is_synthetic_data,
            is_stockout_corrected=demand_result.is_corrected,
        )[0],
        "confidence_score": calculate_confidence_score(
            ros_source=demand_result.source,
            data_sample_size=data_sample_size or demand_result.data_sample_size,
            cap_scale_factor=scale_factor,
            is_synthetic=is_synthetic_data,
            is_stockout_corrected=demand_result.is_corrected,
        )[1],
        "risk_flags": {
            "stockout_risk": weeks_at_final < 2.0,
            "over_allocation_risk": final_qty > 3 * weekly_ros * season_weeks_remaining if (weekly_ros * season_weeks_remaining) > 0 else False,
            "low_confidence": (data_sample_size or demand_result.data_sample_size) < 4,
            "no_history": demand_result.source == "minimum_presentation",
            "heavy_cap_applied": scale_factor < 0.30,
            "grade_defaulted": grade_was_defaulted,
            "synthetic_demand": is_synthetic_data,
        },
        # PHASE 2 PLACEHOLDERS
        "style_dna_match": style_dna_match,
        # Style-analogue audit trail — present iff Tier 1.5 fired. The frontend
        # uses this to render the "based on these prior styles" panel.
        "style_analogue_match": style_analogue_match,
        # BACKWARD COMPATIBLE FIELDS
        "store_ros_attribute": store_ros_attribute or f"{weekly_ros:.1f} units/week ({demand_result.source})",
        "cluster_avg_ros_attribute": cluster_avg_ros_attribute or f"{weekly_ros:.1f} units/week (cluster proxy)",
        "ros_vs_cluster_pct": ros_vs_cluster_pct,
        "current_stock_cover_days": current_stock_cover_days or round(weeks_at_final * 7, 1),
        "display_capacity_available": display_capacity_available,
        "stockout_risk_at_lower_qty": stockout_risk_at_lower_qty,
        "climate_match": climate_match,
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
    
    TODO: Phase 2 — This function implements the full 4-tier fallback with real cluster queries.
    Currently, the engine uses calculate_store_demand_details() which approximates cluster tier
    using grade averages. Future iterations should migrate to this function for true cluster-based
    fallback.
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
