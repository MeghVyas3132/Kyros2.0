from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AllocationLine,
    AllocationSession,
    AllocationStatus,
    BrandSettings,
    BuyPlanLine,
    GRN,
    GRNLine,
    GRNLineReservation,
    InventoryReservationType,
    InventoryState,
    SKU,
    SalesData,
    Season,
    SizeGuide,
    Store,
    StoreDisplayCapacity,
    StoreProductGrade,
    StyleStoreList,
)
from app.services.allocation.cap import apply_inventory_cap
from app.services.allocation.guardrails import apply_guardrails
from app.services.allocation.intelligence import auto_detect_strategy, prioritize_stores, enforce_mva
from app.services.allocation.constants import (
    DEFAULT_COVER_TARGETS,
    DEFAULT_GRADE,
    GRADE_SCORES,
    MINIMUM_ALLOCATION_QTY,
)
from app.services.allocation.demand import (
    DemandSignal,
    TrueDemandResult,
    build_allocation_reasoning,
    calculate_store_demand_details,
    get_min_presentation_qty,
    get_previous_season_id,
    get_season_weeks_remaining,
    load_cluster_ros_averages,
    load_grade_map,
    load_grade_ros_averages,
    load_sales_history,
    preload_stockout_signals,
)
from app.utils.date_utils import utcnow
from app.services.allocation.size_curve import calculate_size_distribution, preload_size_data
from app.services.allocation.store_profile import load_store_profile_map

logger = logging.getLogger(__name__)

ROS_WEIGHT = 0.50
GRADE_WEIGHT = 0.25
COVER_WEIGHT = 0.25
CLIMATE_RULES = {
    "South": {"blocked_fabrics": ["Wool", "Heavy Fleece"]},
    "North": {"blocked_categories_in_summer": []},
}

DEFAULT_BRAND_SETTINGS: dict = {
    "allocation": {
        "experimental_max_stores": 5,
        "experimental_min_units_per_store": 6,
    },
    "cold_start": {
        "scoring_mode": "GRADE_ONLY",
    },
}


def _normalize_category_key(category: str | None) -> str:
    return " ".join(str(category or "").strip().lower().split())


def _normalize_price_band(price_band: str | None) -> str | None:
    cleaned = " ".join(str(price_band or "").strip().upper().split())
    return cleaned or None

@dataclass
class ScoreData:
    score: float
    store_ros: float
    grade_score: int
    current_cover: float
    sample_size: int
    store_grade: str


class AllocationEngine:
    def __init__(self) -> None:
        self._store_cache: dict[UUID, Store] = {}
        self._store_list_cache: dict[UUID, StyleStoreList | None] = {}
        self._grade_cache: dict[tuple[UUID, str, str | None], str] | None = None
        self._display_capacity_cache: dict[tuple[UUID, str], int] = {}
        self._display_capacity_preloaded: bool = False

    async def generate(self, grn_id: UUID, brand_id: UUID, db: AsyncSession) -> AllocationSession:
        # Reset caches per generation run
        self._store_cache = {}
        self._store_list_cache = {}
        self._grade_cache = None
        self._display_capacity_cache = {}
        self._display_capacity_preloaded = False

        grn = await db.scalar(select(GRN).where(GRN.id == grn_id, GRN.brand_id == brand_id))
        if grn is None:
            raise ValueError(f"GRN {grn_id} not found for brand {brand_id}")

        # Fix 1.3: Lock the session row to prevent concurrent runs
        session = await db.scalar(
            select(AllocationSession).where(
                AllocationSession.grn_id == grn_id,
                AllocationSession.brand_id == brand_id,
            ).with_for_update(skip_locked=False)
        )
        if session is not None and session.status == AllocationStatus.APPROVED:
            return session

        stores = (
            await db.execute(
                select(Store).where(
                    Store.brand_id == brand_id,
                    Store.is_active.is_(True),
                )
            )
        ).scalars().all()
        self._store_cache = {store.id: store for store in stores}

        if session is None:
            session = AllocationSession(
                brand_id=brand_id,
                grn_id=grn_id,
                season_id=grn.season_id,
                status=AllocationStatus.DRAFT,
                generated_at=utcnow(),
                total_stores=len(stores),
            )
            db.add(session)
            await db.flush()
        else:
            # Keep GENERATING status if it was set by the Celery dispatch,
            # so the polling frontend doesn't see an intermediate DRAFT.
            if session.status != AllocationStatus.GENERATING:
                session.status = AllocationStatus.DRAFT
            session.generated_at = utcnow()
            session.total_stores = len(stores)

        await db.flush()

        grn_lines = (
            await db.execute(
                select(GRNLine).where(
                    GRNLine.grn_id == grn_id,
                    GRNLine.brand_id == brand_id,
                )
            )
        ).scalars().all()

        sku_ids = list({gl.sku_id for gl in grn_lines})
        sku_rows = (
            await db.execute(
                select(SKU).where(SKU.id.in_(sku_ids), SKU.brand_id == brand_id)
            )
        ).scalars().all()
        sku_map: dict[UUID, SKU] = {s.id: s for s in sku_rows}

        buy_plan_ids = [line.buy_plan_line_id for line in grn_lines if line.buy_plan_line_id is not None]
        buy_plan_map: dict[UUID, BuyPlanLine] = {}
        if buy_plan_ids:
            buy_plan_rows = (
                await db.execute(select(BuyPlanLine).where(BuyPlanLine.id.in_(buy_plan_ids)))
            ).scalars().all()
            buy_plan_map = {line.id: line for line in buy_plan_rows}

        grn_line_ids = [gl.id for gl in grn_lines]
        res_rows = await db.execute(
            select(
                GRNLineReservation.grn_line_id,
                func.coalesce(func.sum(GRNLineReservation.reserved_qty), 0).label("reserved_sum"),
            )
            .join(
                InventoryReservationType,
                and_(
                    InventoryReservationType.id == GRNLineReservation.reservation_type_id,
                    InventoryReservationType.is_active.is_(True),
                    InventoryReservationType.deducts_from_first_allocation.is_(True),
                ),
            )
            .where(GRNLineReservation.grn_line_id.in_(grn_line_ids))
            .group_by(GRNLineReservation.grn_line_id)
        )
        reservation_map: dict[UUID, int] = {row.grn_line_id: int(row.reserved_sum) for row in res_rows.all()}

        existing_lines = (
            await db.execute(select(AllocationLine).where(AllocationLine.session_id == session.id))
        ).scalars().all()
        existing_line_map: dict[tuple[UUID, UUID], AllocationLine] = {
            (line.store_id, line.sku_id): line for line in existing_lines
        }
        existing_lines_by_sku: dict[UUID, list[AllocationLine]] = {}
        for line in existing_lines:
            existing_lines_by_sku.setdefault(line.sku_id, []).append(line)

        previous_season_id = await get_previous_season_id(db, brand_id, grn.season_id)
        season_weeks_remaining = await get_season_weeks_remaining(db, brand_id, grn.season_id)
        min_presentation_qty = await get_min_presentation_qty(db, brand_id)
        grade_map = await load_grade_map(db, brand_id)

        sales_by_store_category = await load_sales_history(
            db=db, brand_id=brand_id, season_id=previous_season_id
        )
        grade_ros_averages = await load_grade_ros_averages(
            db=db, brand_id=brand_id, season_id=previous_season_id
        )
        cluster_ros_averages = await load_cluster_ros_averages(
            db=db, brand_id=brand_id, season_id=previous_season_id
        )
        preloaded_stockout_signals = await preload_stockout_signals(
            db=db, brand_id=brand_id, season_id=previous_season_id
        )
        brand_settings = await self._load_brand_settings(brand_id, db)
        store_profile_map = await load_store_profile_map(brand_id, db)
        inventory = await self._load_latest_inventory(brand_id, db)
        ros_by_attribute = await self._load_ros_by_attribute(brand_id, db)
        await self._preload_display_capacity(brand_id, db)
        preloaded_guides, preloaded_ratios = await preload_size_data(brand_id, db)
        logger.info("Preloaded %d size-guide categories and %d store-level size ratio entries",
                    len(preloaded_guides), len(preloaded_ratios.store_ratios))
        style_dna_cache = {}

        total_units = 0
        processed = 0
        BATCH_SIZE = 500
        batch = []

        # ──────────────────────────────────────────────────────────────
        # STYLE-LEVEL ALLOCATION (Fix 1.1)
        # Group GRN lines by style_code so that all 8 sizes of a style
        # share a single demand/cap/distribution pass.
        # ──────────────────────────────────────────────────────────────
        from collections import defaultdict as _defaultdict

        style_groups: dict[str, list] = _defaultdict(list)
        for grn_line in grn_lines:
            sku = sku_map.get(grn_line.sku_id)
            if sku is None:
                continue
            style_groups[sku.style_code].append(grn_line)

        for style_code, style_grn_lines in style_groups.items():
            # --- Sum available_units across all sizes for this style ---
            style_available_units = 0
            size_available_map: dict[UUID, int] = {}   # sku_id → available
            representative_sku: SKU | None = None

            for grn_line in style_grn_lines:
                sku = sku_map.get(grn_line.sku_id)
                if sku is None:
                    continue
                reserved = reservation_map.get(grn_line.id)
                if reserved is None:
                    reserved = int(grn_line.ecom_reserved_qty or 0) + int(grn_line.ars_reserved_qty or 0)
                avail = max(0, int(grn_line.units_received or 0) - reserved)
                size_available_map[sku.id] = avail
                style_available_units += avail
                if representative_sku is None:
                    representative_sku = sku

            if style_available_units <= 0 or representative_sku is None:
                continue

            sku = representative_sku
            normalized_category = _normalize_category_key(sku.category)

            rule = sku.store_group_rule
            for grn_line in style_grn_lines:
                if grn_line.buy_plan_line_id is not None and grn_line.buy_plan_line_id in buy_plan_map:
                    rule = buy_plan_map[grn_line.buy_plan_line_id].store_group_rule or rule
                    break

            # --- Filter & score stores (same as before, using representative SKU) ---
            eligible_stores = self._filter_stores_for_group_rule(
                stores=stores,
                grade_map=grade_map,
                product_category=normalized_category,
                rule=rule,
            )
            if not eligible_stores:
                logger.warning("No eligible stores for style %s under rule %s", style_code, rule)
                continue

            store_scores = await self.score_stores(
                sku=sku,
                stores=eligible_stores,
                inventory=inventory,
                ros_by_attribute=ros_by_attribute,
                brand_id=brand_id,
                db=db,
                brand_settings=brand_settings,
            )
            eligible_scores = await self.filter_eligible(
                store_scores=store_scores,
                sku=sku,
                inventory=inventory,
                db=db,
                brand_id=brand_id,
            )

            # ──── NEW: PRIORITIZATION LAYER ────
            min_depth_setting = brand_settings.get("min_depth", 3)
            strategy = auto_detect_strategy(
                available_units=style_available_units,
                eligible_store_count=len(eligible_scores),
                risk_level=sku.style_risk_group or "PROVEN",
                min_depth=min_depth_setting,
            )
            prioritized = prioritize_stores(
                eligible_scores=eligible_scores,
                available_units=style_available_units,
                min_depth=min_depth_setting,
                strategy=strategy,
            )
            eligible_scores = prioritized
            eligible_stores = [
                store for store in eligible_stores if store.id in prioritized
            ]
            # ──── END PRIORITIZATION ────

            if not eligible_scores:
                logger.warning("No stores passed eligibility for style %s", style_code)
                continue
            eligible_stores = [self._store_cache[store_id] for store_id in eligible_scores.keys()]

            # --- Compute demand at STYLE level (not per-size) ---
            demand_signals: list[DemandSignal] = []
            store_grade_map: dict[UUID, str] = {}
            for store in eligible_stores:
                grade = grade_map.get((store.id, normalized_category), DEFAULT_GRADE)
                store_grade_map[store.id] = grade
                demand_signals.append(
                    await calculate_store_demand_details(
                        db=db,
                        brand_id=brand_id,
                        sku=sku,
                        store=store,
                        season_weeks_remaining=season_weeks_remaining,
                        fallback_grade=grade,
                        sales_by_store_category=sales_by_store_category,
                        grade_ros_averages=grade_ros_averages,
                        cluster_ros_averages=cluster_ros_averages,
                        min_presentation_qty=min_presentation_qty,
                        previous_season_id=previous_season_id,
                        preloaded_stockout_signals=preloaded_stockout_signals,
                        style_dna_cache=style_dna_cache,
                    )
                )

            store_demands: dict[UUID, int] = {}
            demand_signal_map: dict[UUID, DemandSignal] = {}
            affinity_adjustment_map: dict[UUID, int] = {}
            affinity_multiplier_map: dict[UUID, float] = {}
            for store, signal in zip(eligible_stores, demand_signals):
                style_risk_group = (sku.style_risk_group or "PROVEN").upper()
                grade = store_grade_map[store.id]
                cover_target_weeks = min(
                    self._cover_target_weeks(style_risk_group, grade),
                    max(int(season_weeks_remaining), 1),
                )
                if cover_target_weeks <= 0:
                    store_demands[store.id] = 0
                    demand_signal_map[store.id] = signal
                    affinity_adjustment_map[store.id] = 0
                    affinity_multiplier_map[store.id] = 1.0
                    continue

                profile = store_profile_map.get(store.id)
                affinity_multiplier = self._affinity_multiplier(profile, sku)

                base_ros_with_grade = signal.weekly_ros * signal.grade_multiplier
                adjusted_ros = base_ros_with_grade * affinity_multiplier
                pre_affinity_target = round(base_ros_with_grade * cover_target_weeks)
                raw_target = round(adjusted_ros * cover_target_weeks)
                store_demands[store.id] = int(max(raw_target, min_presentation_qty))
                demand_signal_map[store.id] = signal
                affinity_adjustment_map[store.id] = int(max(raw_target - pre_affinity_target, 0))
                affinity_multiplier_map[store.id] = affinity_multiplier

            total_raw_demand = sum(store_demands.values())
            base_distribution = self.distribute_units(eligible_scores, style_available_units, sku, brand_settings)
            if base_distribution:
                allowed_store_ids = set(base_distribution.keys())
                store_demands = {
                    store_id: qty for store_id, qty in store_demands.items() if store_id in allowed_store_ids
                }
                total_raw_demand = sum(store_demands.values())

            if total_raw_demand <= 0:
                continue

            store_demands, cannibalization_meta = self._apply_story_cannibalization(
                sku=sku,
                allocations=store_demands,
                existing_line_map=existing_line_map,
                sku_map=sku_map,
            )

            # --- Cap at STYLE level (not per-size) ---
            final_allocations = apply_inventory_cap(
                store_demands=store_demands,
                available_qty=style_available_units,
                min_presentation_qty=min_presentation_qty,
                store_grades=store_grade_map,
            )

            # ──── NEW: MVA ENFORCEMENT ────
            final_allocations = enforce_mva(
                allocations=final_allocations,
                store_grades=store_grade_map,
                base_mva=min_presentation_qty,
                eligible_scores=eligible_scores,
            )
            # ──── END MVA ────
            
            # --- Phase 2.1: Guardrails ---
            guardrail_result = apply_guardrails(
                allocations=final_allocations,
                available_units=style_available_units,
                store_grades=store_grade_map,
                brand_config=brand_settings,
            )
            final_allocations = guardrail_result.adjustments

            final_allocations = await self.apply_constraints(final_allocations, style_available_units, sku, db)
            final_allocations = await self.filter_stores_by_size_eligibility(final_allocations, sku, brand_id, db)
            final_allocations = await self._top_up_allocations(
                allocations=final_allocations,
                target_demands=store_demands,
                available_units=style_available_units,
                sku=sku,
                store_scores=eligible_scores,
                brand_id=brand_id,
                db=db,
            )

            # Post-constraints reconciliation
            total_allocated = sum(final_allocations.values())
            if total_allocated > style_available_units:
                logger.warning(
                    "Style %s: allocated %d exceeds available %d. Scaling down.",
                    style_code, total_allocated, style_available_units,
                )
                if total_allocated > 0:
                    scale = style_available_units / total_allocated
                    scaled_allocations = {
                        store_id: max(0, round(qty * scale))
                        for store_id, qty in final_allocations.items()
                    }
                    rounding_overflow = sum(scaled_allocations.values()) - style_available_units
                    if rounding_overflow > 0:
                        for store_id, qty in sorted(
                            scaled_allocations.items(), key=lambda item: item[1], reverse=True,
                        ):
                            if rounding_overflow <= 0:
                                break
                            decrement = min(qty, rounding_overflow)
                            scaled_allocations[store_id] -= decrement
                            rounding_overflow -= decrement
                    final_allocations = {
                        store_id: qty for store_id, qty in scaled_allocations.items() if qty > 0
                    }

            # ──────────────────────────────────────────────────────────
            # SIZE DISTRIBUTION: Split each store's style-level qty
            # into per-size quantities using the existing size curve.
            # Then emit one AllocationLine per (store × size-SKU).
            # ──────────────────────────────────────────────────────────
            # Build a map from size → sku_id for this style
            size_to_sku: dict[str, SKU] = {}
            for grn_line in style_grn_lines:
                _sku = sku_map.get(grn_line.sku_id)
                if _sku is not None and _sku.size:
                    size_to_sku[_sku.size] = _sku

            for store in eligible_stores:
                store_id = store.id
                style_qty = final_allocations.get(store_id, 0)
                raw_demand = store_demands.get(store_id, 0)
                signal = demand_signal_map[store_id]
                style_risk_group = (sku.style_risk_group or "PROVEN").upper()
                cover_target_weeks = min(
                    self._cover_target_weeks(style_risk_group, signal.grade),
                    max(int(season_weeks_remaining), 1),
                )
                profile = store_profile_map.get(store_id)

                # Compute size split for this store's style-level allocation
                size_split: dict[str, int] = {}
                size_distribution_source = "size_guide"
                if style_qty > 0:
                    try:
                        size_split = await calculate_size_distribution(
                            db=db,
                            brand_id=brand_id,
                            sku=sku,
                            store=store,
                            total_qty=style_qty,
                            store_grade=store_grade_map.get(store_id, DEFAULT_GRADE),
                            historical_season_id=previous_season_id,
                            preloaded_guides=preloaded_guides,
                            preloaded_ratios=preloaded_ratios,
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "Size curve failed for style=%s store=%s", style_code, store.store_code,
                            exc_info=True,
                        )
                        size_split = {}

                    if size_split:
                        non_zero_sizes = [qty for qty in size_split.values() if qty > 0]
                        if len(non_zero_sizes) > 1:
                            size_distribution_source = "historical"

                confidence = self.calculate_confidence(
                    ScoreData(
                        score=0.0,
                        store_ros=signal.weekly_ros,
                        grade_score=GRADE_SCORES.get(signal.grade, GRADE_SCORES[DEFAULT_GRADE]),
                        current_cover=0.0,
                        sample_size=signal.data_sample_size,
                        store_grade=signal.grade,
                    ),
                    brand_settings,
                )

                local_scale_factor = (style_qty / raw_demand) if raw_demand > 0 else 1.0
                weeks_cover = (style_qty / signal.weekly_ros) if signal.weekly_ros > 0 else 0.0

                method_reasoning = await self.generate_reasoning(
                    store_id=store_id,
                    sku=sku,
                    qty=style_qty,
                    store_scores=eligible_scores,
                    ros_data=ros_by_attribute,
                    season_weeks_remaining=season_weeks_remaining,
                    db=db,
                )
                cluster_avg = float(method_reasoning.get("cluster_avg_ros_attribute") or 0.0)

                true_demand = TrueDemandResult(
                    weekly_ros=signal.weekly_ros,
                    raw_weekly_ros=signal.weekly_ros,
                    source=signal.ros_source,
                    is_corrected=signal.is_corrected,
                    stockout_week=signal.stockout_week,
                    lost_sales_estimate=signal.lost_sales_estimate,
                    data_sample_size=signal.data_sample_size,
                    cluster_store_count=signal.cluster_store_count,
                )

                cannibal_meta = cannibalization_meta.get(store_id, {})

                reasoning = build_allocation_reasoning(
                    store_id=str(store_id),
                    sku_id=str(sku.id),
                    grade=store_grade_map.get(store_id, DEFAULT_GRADE),
                    demand_result=true_demand,
                    cover_target_weeks=cover_target_weeks,
                    raw_demand_units=raw_demand,
                    final_qty=style_qty,
                    available_qty=int(style_available_units),
                    size_result={
                        "size_split": size_split,
                        "source": "store_historical" if size_distribution_source == "historical" else "brand_size_guide",
                        "season_code": str(previous_season_id) if previous_season_id else None,
                    },
                    season_weeks_remaining=season_weeks_remaining,
                    grade_multiplier=signal.grade_multiplier,
                    category_affinity=profile.category_affinity_score if profile else None,
                    fabric_affinity=profile.fabric_affinity_score if profile else None,
                    category_affinity_label=profile.category_affinity if profile else None,
                    fabric_affinity_label=profile.fabric_affinity if profile else None,
                    affinity_adjustment_units=affinity_adjustment_map.get(store_id),
                    affinity_multiplier=affinity_multiplier_map.get(store_id, 1.0),
                    cannibalization_factor=cannibal_meta.get("factor"),
                    cannibalization_reason=cannibal_meta.get("reason"),
                    colourways_in_story_at_store=cannibal_meta.get("competing_count"),
                    style_dna_match=(
                        {
                            "matched_style_code": signal.matched_style_code,
                            "similarity_score": signal.similarity_score,
                        }
                        if signal.ros_source == "style_dna_analogue" and signal.matched_style_code
                        else None
                    ),
                    excluded_by_capacity=False,
                    exclusion_reason=None,
                    store_ros_attribute=f"{signal.weekly_ros:.1f} units/week ({signal.ros_source})",
                    cluster_avg_ros_attribute=f"{cluster_avg:.1f} units/week (cluster proxy)",
                    ros_vs_cluster_pct=(
                        round(((signal.weekly_ros - cluster_avg) / max(cluster_avg, 0.01)) * 100)
                        if cluster_avg > 0
                        else 0
                    ),
                    current_stock_cover_days=round(weeks_cover * 7, 1),
                    display_capacity_available=method_reasoning.get("display_capacity_available"),
                    stockout_risk_at_lower_qty=(weeks_cover * 0.75) < max(season_weeks_remaining * 0.7, 1),
                    climate_match=method_reasoning.get("climate_match", True),
                    data_sample_size=profile.sample_size if profile else signal.data_sample_size,
                )

                projections = {
                    "size_split": size_split,
                    "size_distribution_source": size_distribution_source,
                    "cap_scale_factor": round(local_scale_factor, 4),
                    "total_demand_before_cap": int(total_raw_demand),
                    "available_qty": int(style_available_units),
                }

                # --- Emit one AllocationLine per size-SKU ---
                if size_split:
                    for size_label, size_qty in size_split.items():
                        size_sku = size_to_sku.get(size_label)
                        if size_sku is None or size_qty <= 0:
                            continue

                        existing_line = existing_line_map.get((store_id, size_sku.id))
                        if existing_line is None:
                            existing_line = AllocationLine(
                                session_id=session.id,
                                brand_id=brand_id,
                                store_id=store_id,
                                sku_id=size_sku.id,
                                ai_reasoning=reasoning,
                            )
                            batch.append(existing_line)
                            existing_line_map[(store_id, size_sku.id)] = existing_line
                        else:
                            existing_line.ai_reasoning = reasoning

                        existing_line.ai_recommended_qty = size_qty
                        existing_line.final_qty = size_qty
                        existing_line.ai_confidence = confidence
                        existing_line.ai_projections = projections

                elif style_qty > 0:
                    # size_split failed — fall back to putting all on representative SKU
                    existing_line = existing_line_map.get((store_id, sku.id))
                    if existing_line is None:
                        existing_line = AllocationLine(
                            session_id=session.id,
                            brand_id=brand_id,
                            store_id=store_id,
                            sku_id=sku.id,
                            ai_reasoning=reasoning,
                        )
                        batch.append(existing_line)
                        existing_line_map[(store_id, sku.id)] = existing_line
                    else:
                        existing_line.ai_reasoning = reasoning

                    existing_line.ai_recommended_qty = style_qty
                    existing_line.final_qty = style_qty
                    existing_line.ai_confidence = confidence
                    existing_line.ai_projections = projections

                # Also emit zero-qty lines for sizes that got 0
                for size_label, size_sku in size_to_sku.items():
                    if size_split.get(size_label, 0) > 0:
                        continue
                    existing_line = existing_line_map.get((store_id, size_sku.id))
                    if existing_line is None:
                        existing_line = AllocationLine(
                            session_id=session.id,
                            brand_id=brand_id,
                            store_id=store_id,
                            sku_id=size_sku.id,
                            ai_reasoning=reasoning,
                        )
                        batch.append(existing_line)
                        existing_line_map[(store_id, size_sku.id)] = existing_line
                    else:
                        existing_line.ai_reasoning = reasoning
                    existing_line.ai_recommended_qty = 0
                    existing_line.final_qty = 0
                    existing_line.ai_confidence = confidence
                    existing_line.ai_projections = projections

                # Batch flush
                if len(batch) >= BATCH_SIZE:
                    db.add_all(batch)
                    await db.flush()
                    batch.clear()

            # Handle stale lines for all SKUs in this style
            touched_store_ids = {store.id for store in eligible_stores}
            for grn_line in style_grn_lines:
                _sku = sku_map.get(grn_line.sku_id)
                if _sku is None:
                    continue
                stale_lines = existing_lines_by_sku.get(_sku.id, [])
                for stale_line in stale_lines:
                    if stale_line.store_id in touched_store_ids:
                        continue

                    stale_reasoning = build_allocation_reasoning(
                        store_id=str(stale_line.store_id),
                        sku_id=str(_sku.id),
                        grade=grade_map.get((stale_line.store_id, normalized_category), DEFAULT_GRADE),
                        demand_result=TrueDemandResult(
                            weekly_ros=0.0, raw_weekly_ros=0.0, source="minimum_presentation",
                            is_corrected=False, stockout_week=None, lost_sales_estimate=None,
                            data_sample_size=0, cluster_store_count=0,
                        ),
                        cover_target_weeks=0, raw_demand_units=0, final_qty=0,
                        available_qty=int(style_available_units),
                        size_result={"size_split": {}, "source": "brand_size_guide", "season_code": None},
                        season_weeks_remaining=season_weeks_remaining, grade_multiplier=1.0,
                        store_ros_attribute="0.0 units/week (not eligible)",
                        cluster_avg_ros_attribute="0.0 units/week (cluster proxy)",
                        ros_vs_cluster_pct=0, current_stock_cover_days=0.0, data_sample_size=0,
                    )
                    stale_reasoning["narrative_demand"] = "This line is not eligible under current store group or constraints."
                    stale_reasoning["narrative_adjustments"] = "No adjustments applied."
                    stale_reasoning["narrative_cap"] = "No scaling required."
                    stale_reasoning["confidence_basis"] = "No historical demand available for this store/style context."
                    stale_line.ai_recommended_qty = 0
                    stale_line.final_qty = 0
                    stale_line.ai_confidence = "LOW"
                    stale_line.ai_reasoning = stale_reasoning
                    stale_line.ai_projections = {
                        "size_split": {}, "size_distribution_source": "size_guide",
                        "cap_scale_factor": 1.0, "total_demand_before_cap": 0,
                        "available_qty": int(style_available_units),
                    }

            style_total_allocated = sum(final_allocations.values())
            if style_total_allocated != style_available_units:
                logger.warning(
                    "Style cap mismatch for style=%s: allocated=%d available=%d",
                    style_code, style_total_allocated, style_available_units,
                )

            total_units += style_total_allocated

            processed += 1
            if processed % 50 == 0:
                logger.info("Allocation progress: %d / %d styles processed", processed, len(style_groups))

        if batch:
            db.add_all(batch)
            await db.flush()
            batch.clear()

        logger.info(
            "Allocation complete: %d total units across %d stores",
            total_units,
            len(stores),
        )
        session.total_skus = len(style_groups)
        session.total_units_recommended = total_units
        session.status = AllocationStatus.UNDER_REVIEW
        await db.flush()
        return session

    def _filter_stores_for_group_rule(
        self,
        stores: list[Store],
        grade_map: dict[tuple[UUID, str], str],
        product_category: str,
        rule: str | None,
    ) -> list[Store]:
        normalized_category = _normalize_category_key(product_category)
        normalized_rule = (rule or "All Stores").strip().upper()
        if normalized_rule in {"ALL STORES", "ALL"}:
            return stores

        if normalized_rule in {"A+ ONLY", "A+_ONLY"}:
            allowed = {"A+"}
        elif normalized_rule in {"A+ & A", "A+_A", "A+ AND A"}:
            allowed = {"A+", "A"}
        elif normalized_rule in {"A+, A & B", "A+_A_B", "A+, A AND B"}:
            allowed = {"A+", "A", "B"}
        else:
            return stores

        return [
            store
            for store in stores
            if grade_map.get((store.id, normalized_category), DEFAULT_GRADE) in allowed
        ]

    def _confidence_from_ros_source(self, source: str) -> str:
        if source == "store_historical":
            return "HIGH"
        if source == "grade_average":
            return "MEDIUM"
        return "LOW"

    async def _load_latest_inventory(
        self,
        brand_id: UUID,
        db: AsyncSession,
    ) -> dict[tuple[str, UUID], InventoryState]:
        latest_date = await db.scalar(
            select(func.max(InventoryState.snapshot_date)).where(InventoryState.brand_id == brand_id)
        )
        if latest_date is None:
            return {}
        rows = (
            await db.execute(
                select(InventoryState).where(
                    InventoryState.brand_id == brand_id,
                    InventoryState.snapshot_date == latest_date,
                )
            )
        ).scalars().all()
        return {(row.location_id, row.sku_id): row for row in rows}

    async def _load_ros_by_attribute(
        self,
        brand_id: UUID,
        db: AsyncSession,
    ) -> dict[tuple[UUID, str], dict[str, float]]:
        result = await db.execute(
            select(
                SalesData.store_id,
                SKU.category,
                SKU.fabric,
                SKU.price_band,
                func.coalesce(func.sum(SalesData.units_sold), 0).label("units"),
                func.count(func.nullif(SalesData.was_in_stock, False)).label("weeks"),
            )
            .join(SKU, SKU.id == SalesData.sku_id)
            .where(SalesData.brand_id == brand_id)
            .group_by(SalesData.store_id, SKU.category, SKU.fabric, SKU.price_band)
        )
        ros_map: dict[tuple[UUID, str], dict[str, float]] = {}
        for store_id, category, fabric, price_band, units, weeks in result.all():
            key = f"{category}_{fabric}_{price_band}"
            days = max(int(weeks or 0) * 7, 1)
            ros = float(units) / days
            ros_map[(store_id, key)] = {"ros": ros, "sample_size": float(weeks or 0)}
        return ros_map

    async def _load_brand_settings(self, brand_id: UUID, db: AsyncSession) -> dict:
        config = await db.scalar(select(BrandSettings.config).where(BrandSettings.brand_id == brand_id))
        if not isinstance(config, dict):
            return DEFAULT_BRAND_SETTINGS.copy()

        merged = DEFAULT_BRAND_SETTINGS.copy()
        for key, value in config.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged

    async def _load_all_grades(self, brand_id: UUID, db: AsyncSession) -> dict[tuple[UUID, str, str | None], str]:
        """Batch-load every StoreProductGrade row into a dict for O(1) lookups."""
        if not hasattr(self, "_grade_cache") or self._grade_cache is None:
            result = await db.execute(
                select(
                    StoreProductGrade.store_id,
                    StoreProductGrade.product_category,
                    StoreProductGrade.price_band,
                    StoreProductGrade.grade,
                ).where(StoreProductGrade.brand_id == brand_id)
            )
            cache: dict[tuple[UUID, str, str | None], str] = {}
            for store_id, product_category, price_band, grade in result.all():
                cache[(
                    store_id,
                    _normalize_category_key(product_category),
                    _normalize_price_band(price_band),
                )] = grade
            self._grade_cache = cache
        return self._grade_cache

    async def get_store_grade_for_sku(
        self,
        store_id: UUID,
        product_category: str,
        price_band: str | None,
        brand_id: UUID,
        db: AsyncSession,
    ) -> str:
        grades = await self._load_all_grades(brand_id, db)
        normalized_category = _normalize_category_key(product_category)
        normalized_price_band = _normalize_price_band(price_band)

        # exact match: store + product + price_band
        exact = grades.get((store_id, normalized_category, normalized_price_band))
        if exact:
            return exact

        # fallback: store + product, no price_band
        product_level = grades.get((store_id, normalized_category, None))
        if product_level:
            return product_level

        logger.debug(
            "No grade found for store=%s product=%s price_band=%s brand=%s. Defaulting to %s.",
            store_id,
            product_category,
            price_band,
            brand_id,
            DEFAULT_GRADE,
        )
        return DEFAULT_GRADE

    async def score_stores(
        self,
        sku: SKU,
        stores: list[Store],
        inventory: dict[tuple[str, UUID], InventoryState],
        ros_by_attribute: dict[tuple[UUID, str], dict[str, float]],
        brand_id: UUID,
        db: AsyncSession,
        brand_settings: dict,
    ) -> dict[UUID, ScoreData]:
        attribute_key = f"{sku.category}_{sku.fabric}_{sku.price_band}"
        scores: dict[UUID, ScoreData] = {}
        scoring_mode = str(
            brand_settings.get("cold_start", {}).get("scoring_mode", "GRADE_ONLY")
        ).upper()

        # Phase 1: Collect raw values for all stores
        raw_data: dict[UUID, tuple[float, int, float, float, int, str]] = {}
        for store in stores:
            ros_entry = ros_by_attribute.get((store.id, attribute_key), {})
            sample_size = int(ros_entry.get("sample_size", 0))
            store_ros = float(ros_entry.get("ros", 0))
            store_grade = await self.get_store_grade_for_sku(
                store_id=store.id,
                product_category=sku.category,
                price_band=sku.price_band,
                brand_id=brand_id,
                db=db,
            )
            grade_score = GRADE_SCORES.get(store_grade, GRADE_SCORES[DEFAULT_GRADE])
            current_cover = self._attribute_cover(store.id, inventory)

            ros_component = store_ros
            if sample_size == 0 and scoring_mode == "GRADE_ONLY":
                ros_component = 0.0

            raw_data[store.id] = (ros_component, grade_score, current_cover, store_ros, sample_size, store_grade)

        if not raw_data:
            return scores

        # Phase 2: Min-max normalize each component to [0, 1]
        store_ids = list(raw_data.keys())
        ros_vals = [raw_data[sid][0] for sid in store_ids]
        grade_vals = [float(raw_data[sid][1]) for sid in store_ids]
        cover_inv_vals = [1.0 / max(raw_data[sid][2], 0.1) for sid in store_ids]

        def _normalize(vals: list[float]) -> list[float]:
            lo, hi = min(vals), max(vals)
            if hi <= lo:
                return [0.5] * len(vals)
            return [(v - lo) / (hi - lo) for v in vals]

        norm_ros = _normalize(ros_vals)
        norm_grade = _normalize(grade_vals)
        norm_cover = _normalize(cover_inv_vals)

        # Phase 3: Apply weights to normalized components
        for i, store_id in enumerate(store_ids):
            ros_component, grade_score, current_cover, store_ros, sample_size, store_grade = raw_data[store_id]
            score = (
                (ROS_WEIGHT * norm_ros[i])
                + (GRADE_WEIGHT * norm_grade[i])
                + (COVER_WEIGHT * norm_cover[i])
            )
            scores[store_id] = ScoreData(
                score=score,
                store_ros=store_ros,
                grade_score=grade_score,
                current_cover=current_cover,
                sample_size=sample_size,
                store_grade=store_grade,
            )

        return scores

    def _attribute_cover(
        self,
        store_id: UUID,
        inventory: dict[tuple[str, UUID], InventoryState],
    ) -> float:
        covers: list[float] = []
        for (location_id, _), state in inventory.items():
            if location_id != str(store_id):
                continue
            ros = float(state.ros_7d or 0)
            if ros <= 0:
                continue
            covers.append(float(state.units_on_hand) / max(ros, 0.01))
        if not covers:
            return 14.0
        return sum(covers) / len(covers)

    async def _load_style_store_list(
        self,
        store_list_id: UUID | None,
        brand_id: UUID,
        db: AsyncSession,
    ) -> StyleStoreList | None:
        if store_list_id is None:
            return None
        if store_list_id not in self._store_list_cache:
            row = await db.scalar(
                select(StyleStoreList).where(
                    StyleStoreList.id == store_list_id,
                    StyleStoreList.brand_id == brand_id,
                )
            )
            self._store_list_cache[store_list_id] = row
        return self._store_list_cache[store_list_id]

    async def filter_eligible(
        self,
        store_scores: dict[UUID, ScoreData],
        sku: SKU,
        inventory: dict[tuple[str, UUID], InventoryState],
        db: AsyncSession,
        brand_id: UUID,
    ) -> dict[UUID, ScoreData]:
        del inventory  # TODO: confirm with spec - inventory-specific eligibility not yet required.

        eligible: dict[UUID, ScoreData] = {}
        store_list = await self._load_style_store_list(sku.store_list_id, brand_id, db)
        store_list_ids = set(store_list.store_ids) if store_list is not None else None
        required_min_grade = sku.resolved_min_grade

        for store_id, score_data in store_scores.items():
            store = self._store_cache[store_id]

            if store_list_ids is not None and store_id not in store_list_ids:
                continue

            if required_min_grade:
                if GRADE_SCORES.get(score_data.store_grade, 1) < GRADE_SCORES.get(required_min_grade, 1):
                    continue

            if not self._climate_match(store, sku):
                continue

            remaining_capacity = await self._remaining_display_capacity(store_id, sku.category, db)
            if remaining_capacity <= 0:
                continue

            eligible[store_id] = score_data

        return eligible

    def _climate_match(self, store: Store, sku: SKU) -> bool:
        zone = (store.climate_zone or "").strip()
        if zone == "South":
            blocked_fabrics = CLIMATE_RULES["South"]["blocked_fabrics"]
            if sku.fabric in blocked_fabrics:
                return False
        return True

    async def _preload_display_capacity(self, brand_id: UUID, db: AsyncSession) -> int:
        rows = await db.execute(
            select(
                StoreDisplayCapacity.store_id,
                StoreDisplayCapacity.category,
                StoreDisplayCapacity.max_units,
                StoreDisplayCapacity.max_styles,
            ).where(StoreDisplayCapacity.brand_id == brand_id)
        )
        self._display_capacity_cache = {}
        for store_id, category, max_units, max_styles in rows.all():
            self._display_capacity_cache[(store_id, _normalize_category_key(category))] = int(
                max_units if max_units is not None else (max_styles or 0) * 6
            )
        self._display_capacity_preloaded = True
        return len(self._display_capacity_cache)

    async def _remaining_display_capacity(self, store_id: UUID, category: str, db: AsyncSession) -> int:
        cache_key = (store_id, _normalize_category_key(category))
        cached = self._display_capacity_cache.get(cache_key)
        if cached is not None:
            return cached
        if self._display_capacity_preloaded:
            return 999

        cap = await db.scalar(
            select(StoreDisplayCapacity).where(
                StoreDisplayCapacity.store_id == store_id,
                func.lower(func.trim(StoreDisplayCapacity.category)) == _normalize_category_key(category),
            )
        )
        if cap is None:
            return 999
        resolved = int(cap.max_units if cap.max_units is not None else (cap.max_styles or 0) * 6)
        self._display_capacity_cache[cache_key] = resolved
        return resolved

    def distribute_units(
        self,
        eligible_stores: dict[UUID, ScoreData],
        available_units: int,
        sku: SKU,
        brand_settings: dict,
    ) -> dict[UUID, int]:
        if available_units <= 0 or not eligible_stores:
            return {}

        risk_level = (sku.resolved_risk_level or "PROVEN").upper()
        allocation_cfg = brand_settings.get("allocation", {})
        if risk_level == "EXPERIMENTAL":
            max_stores = int(allocation_cfg.get("experimental_max_stores", 5))
            min_units = int(allocation_cfg.get("experimental_min_units_per_store", 6))
            return self._distribute_concentrated(eligible_stores, available_units, max_stores, min_units)

        standard_min_units = int(allocation_cfg.get("standard_min_units_per_store", MINIMUM_ALLOCATION_QTY))
        return self._distribute_standard(
            eligible_stores,
            available_units,
            min_units_per_store=standard_min_units,
        )

    def _distribute_standard(
        self,
        eligible_stores: dict[UUID, ScoreData],
        available_units: int,
        min_units_per_store: int = MINIMUM_ALLOCATION_QTY,
    ) -> dict[UUID, int]:
        total_score = sum(score.score for score in eligible_stores.values())
        if total_score <= 0:
            split = max(1, available_units // len(eligible_stores))
            return {store_id: split for store_id in eligible_stores}

        raw_distribution: dict[UUID, int] = {}
        for store_id, score_data in eligible_stores.items():
            proportion = score_data.score / total_score
            raw_distribution[store_id] = max(0, round(available_units * proportion))

        # Keep rounded distribution sum aligned with available units.
        current_total = sum(raw_distribution.values())
        diff = available_units - current_total
        if diff > 0:
            top_store = max(eligible_stores.keys(), key=lambda sid: eligible_stores[sid].score)
            raw_distribution[top_store] += diff
        elif diff < 0:
            remaining = abs(diff)
            ranked = sorted(raw_distribution.items(), key=lambda item: item[1], reverse=True)
            for store_id, qty in ranked:
                if remaining <= 0:
                    break
                if qty <= 0:
                    continue
                decrement = min(qty, remaining)
                raw_distribution[store_id] -= decrement
                remaining -= decrement

        min_units = max(1, int(min_units_per_store))

        # If inventory cannot support minimum units for every eligible store,
        # preserve proportional spread instead of collapsing to one/few stores.
        required_for_minimums = len(eligible_stores) * min_units
        if available_units < required_for_minimums:
            return {store_id: qty for store_id, qty in raw_distribution.items() if qty > 0}

        final: dict[UUID, int] = {}
        below_min: list[UUID] = []
        for store_id, qty in raw_distribution.items():
            if qty >= min_units:
                final[store_id] = qty
            else:
                below_min.append(store_id)

        if below_min and final:
            redistributable = sum(raw_distribution[store_id] for store_id in below_min)
            # Distribute proportionally to ALL above-minimum stores, not just top
            total_above = sum(final.values())
            if total_above > 0:
                added = 0
                sorted_final = sorted(final.keys(), key=lambda sid: eligible_stores[sid].score, reverse=True)
                for store_id in sorted_final:
                    share = round(redistributable * final[store_id] / total_above)
                    final[store_id] += share
                    added += share
                # Fix rounding remainder
                remainder = redistributable - added
                if remainder != 0 and sorted_final:
                    final[sorted_final[0]] += remainder
        elif below_min and not final:
            top_store = max(eligible_stores.keys(), key=lambda sid: eligible_stores[sid].score)
            final[top_store] = available_units

        current_total = sum(final.values())
        diff = available_units - current_total
        if diff != 0 and final:
            top_store = max(final.keys(), key=lambda sid: eligible_stores[sid].score)
            final[top_store] += diff

        return {store_id: qty for store_id, qty in final.items() if qty > 0}

    def _distribute_concentrated(
        self,
        eligible_stores: dict[UUID, ScoreData],
        available_units: int,
        max_stores: int,
        min_units_per_store: int,
    ) -> dict[UUID, int]:
        ranked = sorted(eligible_stores.items(), key=lambda item: item[1].score, reverse=True)
        if not ranked:
            return {}

        affordable_stores = min(max_stores, available_units // max(min_units_per_store, 1))
        if affordable_stores <= 0:
            return {ranked[0][0]: available_units}

        selected = ranked[:affordable_stores]
        per_store = available_units // affordable_stores
        remainder = available_units % affordable_stores

        return {
            store_id: per_store + (1 if idx < remainder else 0)
            for idx, (store_id, _) in enumerate(selected)
            if per_store + (1 if idx < remainder else 0) > 0
        }

    def _is_size_allowed_for_grade(self, applies_to_grades: str, store_grade: str) -> bool:
        if applies_to_grades == "ALL":
            return True
        if applies_to_grades == "A+_ONLY":
            return store_grade == "A+"
        if applies_to_grades == "A+_A":
            return store_grade in {"A+", "A"}
        if applies_to_grades == "A+_A_B":
            return store_grade in {"A+", "A", "B"}
        return True

    async def filter_stores_by_size_eligibility(
        self,
        allocation: dict[UUID, int],
        sku: SKU,
        brand_id: UUID,
        db: AsyncSession,
    ) -> dict[UUID, int]:
        """
        Remove stores that cannot receive this SKU's size based on the size guide.
        A size guide entry with min_max_ratio=0 means this size is never allocated.
        A size guide entry with applies_to_grades restricts which store grades receive it.
        
        This does NOT distribute units across sizes — that happens per-store later
        via calculate_size_distribution() in the main loop.
        """
        if not allocation:
            return {}
        if not sku.size:
            return allocation

        size_guide = await db.scalar(
            select(SizeGuide).where(
                SizeGuide.brand_id == brand_id,
                SizeGuide.product_category == sku.category,
                SizeGuide.size == sku.size,
            )
        )
        if size_guide is None:
            return allocation
        if size_guide.min_max_ratio <= 0:
            return {}

        filtered: dict[UUID, int] = {}
        for store_id, qty in allocation.items():
            store_grade = await self.get_store_grade_for_sku(
                store_id=store_id,
                product_category=sku.category,
                price_band=sku.price_band,
                brand_id=brand_id,
                db=db,
            )
            if self._is_size_allowed_for_grade(size_guide.applies_to_grades, store_grade):
                filtered[store_id] = qty
        return filtered

    async def apply_constraints(
        self,
        allocation: dict[UUID, int],
        available_units: int,
        sku: SKU,
        db: AsyncSession,
        existing_allocations: dict[UUID, int] | None = None,
    ) -> dict[UUID, int]:
        constrained: dict[UUID, int] = {}
        already_allocated = existing_allocations or {}
        total_allocated = sum(int(qty or 0) for qty in already_allocated.values())
        if total_allocated >= available_units:
            return {}

        sorted_stores = sorted(allocation.items(), key=lambda item: item[1], reverse=True)
        for store_id, qty in sorted_stores:
            remaining_capacity = await self._remaining_display_capacity(store_id, sku.category, db)
            current_store_allocation = int(already_allocated.get(store_id, 0))
            capacity_room = max(remaining_capacity - current_store_allocation, 0)
            qty = min(qty, capacity_room)
            remaining_available = available_units - total_allocated
            qty = min(qty, max(remaining_available, 0))

            if qty > 0:
                constrained[store_id] = qty
                total_allocated += qty

            if total_allocated >= available_units:
                break

        return constrained

    async def _top_up_allocations(
        self,
        allocations: dict[UUID, int],
        target_demands: dict[UUID, int],
        available_units: int,
        sku: SKU,
        store_scores: dict[UUID, ScoreData],
        brand_id: UUID,
        db: AsyncSession,
    ) -> dict[UUID, int]:
        current = {store_id: int(qty or 0) for store_id, qty in allocations.items() if int(qty or 0) > 0}
        remaining = max(0, available_units - sum(current.values()))
        if remaining <= 0:
            return current

        residual_demands = {
            store_id: max(int(target_demands.get(store_id, 0)) - int(current.get(store_id, 0)), 0)
            for store_id in target_demands.keys()
        }
        residual_demands = {store_id: qty for store_id, qty in residual_demands.items() if qty > 0}
        if not residual_demands:
            return current

        incremental = apply_inventory_cap(
            store_demands=residual_demands,
            available_qty=remaining,
            min_presentation_qty=0,
            store_grades=None,
        )
        incremental = await self.apply_constraints(
            allocation=incremental,
            available_units=available_units,
            sku=sku,
            db=db,
            existing_allocations=current,
        )
        incremental = await self.filter_stores_by_size_eligibility(incremental, sku, brand_id, db)
        if not incremental:
            return current

        ranked_store_ids = sorted(
            incremental.keys(),
            key=lambda sid: store_scores[sid].score if sid in store_scores else 0.0,
            reverse=True,
        )
        for store_id in ranked_store_ids:
            qty = int(incremental.get(store_id, 0))
            if qty <= 0:
                continue
            current[store_id] = int(current.get(store_id, 0)) + qty

        return current

    def _affinity_multiplier(self, profile, sku: SKU) -> float:
        if profile is None:
            return 1.0

        multiplier = 1.0
        if (
            profile.category_affinity
            and sku.category
            and profile.category_affinity.strip().lower() == sku.category.strip().lower()
            and profile.category_affinity_score
            and profile.category_affinity_score > 1.0
        ):
            multiplier *= min(float(profile.category_affinity_score), 1.5)

        if (
            profile.fabric_affinity
            and sku.fabric
            and profile.fabric_affinity.strip().lower() == sku.fabric.strip().lower()
            and profile.fabric_affinity_score
            and profile.fabric_affinity_score > 1.0
        ):
            multiplier *= min(float(profile.fabric_affinity_score), 1.5)

        return min(multiplier, 1.8)

    def _apply_story_cannibalization(
        self,
        sku: SKU,
        allocations: dict[UUID, int],
        existing_line_map: dict[tuple[UUID, UUID], AllocationLine],
        sku_map: dict[UUID, SKU],
    ) -> tuple[dict[UUID, int], dict[UUID, dict[str, object]]]:
        if not allocations or not sku.story:
            return allocations, {}

        normalized_story = sku.story.strip().lower()
        normalized_fabric = (sku.fabric or "").strip().lower()
        normalized_sub_story = (sku.sub_story or "").strip().lower()

        adjusted: dict[UUID, int] = {}
        meta: dict[UUID, dict[str, object]] = {}

        for store_id, qty in allocations.items():
            if qty <= 0:
                continue

            competing_count = 0
            for (candidate_store_id, candidate_sku_id), line in existing_line_map.items():
                if candidate_store_id != store_id or candidate_sku_id == sku.id:
                    continue

                existing_qty = int(line.final_qty or line.ai_recommended_qty or 0)
                if existing_qty <= 0:
                    continue

                candidate_sku = sku_map.get(candidate_sku_id)
                if candidate_sku is None or not candidate_sku.story:
                    continue

                if candidate_sku.story.strip().lower() != normalized_story:
                    continue

                same_fabric = (
                    normalized_fabric
                    and candidate_sku.fabric
                    and candidate_sku.fabric.strip().lower() == normalized_fabric
                )
                same_sub_story = (
                    normalized_sub_story
                    and candidate_sku.sub_story
                    and candidate_sku.sub_story.strip().lower() == normalized_sub_story
                )

                if same_fabric or same_sub_story:
                    competing_count += 1

            factor = 0.65 if competing_count > 0 else 1.0
            adjusted_qty = max(0, int(round(qty * factor)))
            adjusted[store_id] = adjusted_qty

            if factor < 1.0:
                meta[store_id] = {
                    "factor": factor,
                    "competing_count": competing_count,
                    "reason": f"Story concentration detected ({competing_count} competing colourways).",
                }

        return adjusted, meta

    async def generate_reasoning(
        self,
        store_id: UUID,
        sku: SKU,
        qty: int,
        store_scores: dict[UUID, ScoreData],
        ros_data: dict[tuple[UUID, str], dict[str, float]],
        season_weeks_remaining: int,
        db: AsyncSession,
    ) -> dict:
        store = self._store_cache[store_id]
        attribute_key = f"{sku.category}_{sku.fabric}_{sku.price_band}"

        cluster_store_ids = [
            s.id for s in self._store_cache.values() if s.cluster_id == store.cluster_id
        ]
        cluster_values = [
            float(ros_data.get((sid, attribute_key), {}).get("ros", 0.0)) for sid in cluster_store_ids
        ]
        cluster_values = [value for value in cluster_values if value > 0]
        cluster_avg = sum(cluster_values) / len(cluster_values) if cluster_values else 0.0

        score = store_scores[store_id]
        store_ros = score.store_ros
        current_cover = score.current_cover
        capacity_available = await self._remaining_display_capacity(store_id, sku.category, db)
        weeks_cover = qty / max(store_ros, 0.01) / 7

        return {
            "store_grade": score.store_grade,
            "store_ros_attribute": round(store_ros, 2),
            "cluster_avg_ros_attribute": round(cluster_avg, 2),
            "ros_vs_cluster_pct": round(((store_ros - cluster_avg) / max(cluster_avg, 0.01)) * 100)
            if cluster_avg > 0
            else 0,
            "current_stock_cover_days": round(current_cover, 1),
            "display_capacity_available": capacity_available,
            "season_weeks_remaining": season_weeks_remaining,
            "weeks_cover_at_recommended": round(weeks_cover, 1),
            "weeks_cover_at_minus_25pct": round((qty * 0.75) / max(store_ros, 0.01) / 7, 1),
            "weeks_cover_at_plus_25pct": round((qty * 1.25) / max(store_ros, 0.01) / 7, 1),
            "stockout_risk_at_lower_qty": (qty * 0.75) / max(store_ros, 0.01) / 7
            < season_weeks_remaining * 0.7,
            "climate_match": self._climate_match(store, sku),
            "data_sample_size": score.sample_size,
            "confidence_basis": f"Based on {score.sample_size} comparable store-weeks",
        }

    async def _season_weeks_remaining(self, sku: SKU, db: AsyncSession) -> int:
        season = None
        if sku.season_id:
            season = await db.scalar(select(Season).where(Season.id == sku.season_id))
        if season is None:
            return 8
        today = date.today()
        if season.end_date <= today:
            return 1
        return max(1, (season.end_date - today).days // 7)

    def calculate_confidence(self, score_data: ScoreData, brand_settings: dict) -> str:
        if score_data.sample_size == 0:
            scoring_mode = str(
                brand_settings.get("cold_start", {}).get("scoring_mode", "GRADE_ONLY")
            ).upper()
            if scoring_mode == "GRADE_ONLY":
                return "LOW"

        if score_data.sample_size >= 20:
            return "HIGH"
        if score_data.sample_size >= 5:
            return "MEDIUM"
        return "LOW"

    def _cover_target_weeks(self, style_risk_group: str, grade: str) -> int:
        risk = (style_risk_group or "PROVEN").upper()
        normalized_grade = grade if grade in GRADE_SCORES else DEFAULT_GRADE
        return DEFAULT_COVER_TARGETS.get((risk, normalized_grade), DEFAULT_COVER_TARGETS[("PROVEN", normalized_grade)])

    def _build_demand_narrative(self, signal: DemandSignal) -> str:
        if signal.is_corrected:
            return (
                f"Demand uses stockout-corrected ROS of {signal.weekly_ros:.1f} units/week "
                f"from {signal.ros_source} history."
            )
        return f"Demand uses ROS of {signal.weekly_ros:.1f} units/week from {signal.ros_source} history."

    def _build_adjustment_narrative(self, grade: str, grade_multiplier: float) -> str:
        if abs(grade_multiplier - 1.0) < 0.01:
            return f"No grade uplift/penalty applied for grade {grade}."
        if grade_multiplier > 1.0:
            return f"Grade {grade} uplift applied (+{(grade_multiplier - 1) * 100:.0f}%)."
        return f"Grade {grade} guardrail applied ({(grade_multiplier - 1) * 100:.0f}%)."

    def _build_cap_narrative(
        self,
        raw_demand: int,
        final_qty: int,
        local_scale_factor: float,
        available_units: int,
    ) -> str:
        if raw_demand <= 0:
            return "No demand generated for this store under current eligibility and cover targets."
        if final_qty == raw_demand:
            return "No cap reduction required; recommendation fits available inventory."
        return (
            "Inventory cap applied: "
            f"{raw_demand} -> {final_qty} units (scale {local_scale_factor:.2f}) "
            f"with {available_units} units available at style level."
        )

    def _build_confidence_basis(self, signal: DemandSignal) -> str:
        if signal.data_sample_size <= 0:
            return "Based on fallback demand source due to limited historical observations."
        return (
            f"Based on {signal.data_sample_size} historical observations from "
            f"{signal.ros_source} demand source."
        )
