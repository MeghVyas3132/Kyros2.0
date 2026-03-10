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
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

ROS_WEIGHT = 0.50
GRADE_WEIGHT = 0.25
COVER_WEIGHT = 0.25
MINIMUM_ALLOCATION_QTY = 6

GRADE_SCORES = {"A+": 5, "A": 4, "B": 3, "C": 2}
DEFAULT_GRADE = "C"

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

    async def generate(self, grn_id: UUID, brand_id: UUID, db: AsyncSession) -> AllocationSession:
        grn = await db.scalar(select(GRN).where(GRN.id == grn_id, GRN.brand_id == brand_id))
        if grn is None:
            raise ValueError(f"GRN {grn_id} not found for brand {brand_id}")

        session = await db.scalar(
            select(AllocationSession).where(
                AllocationSession.grn_id == grn_id,
                AllocationSession.brand_id == brand_id,
            )
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

        inventory = await self._load_latest_inventory(brand_id, db)
        ros_data = await self._load_ros_by_attribute(brand_id, db)
        brand_settings = await self._load_brand_settings(brand_id, db)

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
            session.status = AllocationStatus.DRAFT
            session.generated_at = utcnow()
            session.total_stores = len(stores)
            existing_lines = (
                await db.execute(select(AllocationLine).where(AllocationLine.session_id == session.id))
            ).scalars().all()
            for line in existing_lines:
                await db.delete(line)
            await db.flush()

        grn_lines = (
            await db.execute(
                select(GRNLine).where(
                    GRNLine.grn_id == grn_id,
                    GRNLine.brand_id == brand_id,
                )
            )
        ).scalars().all()

        allocation_lines: list[AllocationLine] = []
        total_units = 0

        for grn_line in grn_lines:
            sku = await db.scalar(
                select(SKU).where(SKU.id == grn_line.sku_id, SKU.brand_id == brand_id)
            )
            if sku is None:
                continue

            available_units = await self.get_available_for_first_allocation(grn_line, db)
            if available_units <= 0:
                logger.warning(
                    "Skipping GRN line %s as available_for_first_allocation=%s",
                    grn_line.id,
                    available_units,
                )
                continue

            scores = await self.score_stores(sku, stores, inventory, ros_data, brand_id, db, brand_settings)
            eligible = await self.filter_eligible(scores, sku, inventory, db, brand_id)
            raw = self.distribute_units(eligible, available_units, sku, brand_settings)
            sized = await self.apply_size_curves(raw, sku, brand_id, db)
            constrained = await self.apply_constraints(sized, available_units, grn_line, db)

            for store_id, qty in constrained.items():
                reasoning = await self.generate_reasoning(
                    store_id=store_id,
                    sku=sku,
                    qty=qty,
                    store_scores=scores,
                    ros_data=ros_data,
                    db=db,
                )
                confidence = self.calculate_confidence(
                    score_data=scores[store_id],
                    brand_settings=brand_settings,
                )
                allocation_lines.append(
                    AllocationLine(
                        session_id=session.id,
                        brand_id=brand_id,
                        store_id=store_id,
                        sku_id=sku.id,
                        ai_recommended_qty=qty,
                        ai_confidence=confidence,
                        ai_reasoning=reasoning,
                        ai_projections={
                            "weeks_cover": reasoning["weeks_cover_at_recommended"],
                            "projected_sellthrough": min(
                                1.0,
                                reasoning["weeks_cover_at_recommended"]
                                / max(reasoning["season_weeks_remaining"], 1),
                            ),
                        },
                    )
                )
                total_units += qty

        session.total_skus = len(grn_lines)
        session.total_units_recommended = total_units
        session.status = AllocationStatus.UNDER_REVIEW
        db.add_all(allocation_lines)
        await db.flush()
        return session

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

    async def get_store_grade_for_sku(
        self,
        store_id: UUID,
        product_category: str,
        price_band: str | None,
        brand_id: UUID,
        db: AsyncSession,
    ) -> str:
        exact = await db.scalar(
            select(StoreProductGrade.grade).where(
                StoreProductGrade.brand_id == brand_id,
                StoreProductGrade.store_id == store_id,
                StoreProductGrade.product_category == product_category,
                StoreProductGrade.price_band == price_band,
            )
        )
        if exact:
            return exact

        product_level = await db.scalar(
            select(StoreProductGrade.grade).where(
                StoreProductGrade.brand_id == brand_id,
                StoreProductGrade.store_id == store_id,
                StoreProductGrade.product_category == product_category,
                StoreProductGrade.price_band.is_(None),
            )
        )
        if product_level:
            return product_level

        logger.warning(
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

            score = (
                (ROS_WEIGHT * ros_component)
                + (GRADE_WEIGHT * grade_score)
                + (COVER_WEIGHT * (1 / max(current_cover, 0.1)))
            )
            scores[store.id] = ScoreData(
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
        required_min_grade = sku.resolved_min_grade

        for store_id, score_data in store_scores.items():
            store = self._store_cache[store_id]

            if store_list is not None and store_id not in set(store_list.store_ids):
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

    async def _remaining_display_capacity(self, store_id: UUID, category: str, db: AsyncSession) -> int:
        cap = await db.scalar(
            select(StoreDisplayCapacity).where(
                StoreDisplayCapacity.store_id == store_id,
                StoreDisplayCapacity.category == category,
            )
        )
        if cap is None:
            return 999
        return cap.max_units or (cap.max_styles * 6)

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
        if risk_level == "EXPERIMENTAL":
            allocation_cfg = brand_settings.get("allocation", {})
            max_stores = int(allocation_cfg.get("experimental_max_stores", 5))
            min_units = int(allocation_cfg.get("experimental_min_units_per_store", 6))
            return self._distribute_concentrated(eligible_stores, available_units, max_stores, min_units)

        return self._distribute_standard(eligible_stores, available_units)

    def _distribute_standard(
        self,
        eligible_stores: dict[UUID, ScoreData],
        available_units: int,
    ) -> dict[UUID, int]:
        total_score = sum(score.score for score in eligible_stores.values())
        if total_score <= 0:
            split = max(1, available_units // len(eligible_stores))
            return {store_id: split for store_id in eligible_stores}

        raw_distribution: dict[UUID, int] = {}
        for store_id, score_data in eligible_stores.items():
            proportion = score_data.score / total_score
            raw_distribution[store_id] = max(0, round(available_units * proportion))

        final: dict[UUID, int] = {}
        below_min: list[UUID] = []
        for store_id, qty in raw_distribution.items():
            if qty >= MINIMUM_ALLOCATION_QTY:
                final[store_id] = qty
            else:
                below_min.append(store_id)

        if below_min and final:
            redistributable = sum(raw_distribution[store_id] for store_id in below_min)
            top_store = max(final.keys(), key=lambda sid: eligible_stores[sid].score)
            final[top_store] += redistributable
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

    async def apply_size_curves(
        self,
        allocation: dict[UUID, int],
        sku: SKU,
        brand_id: UUID,
        db: AsyncSession,
    ) -> dict[UUID, int]:
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
        grn_line: GRNLine,
        db: AsyncSession,
    ) -> dict[UUID, int]:
        constrained: dict[UUID, int] = {}
        total_allocated = 0
        sku = await db.scalar(select(SKU).where(SKU.id == grn_line.sku_id))
        if sku is None:
            return {}

        sorted_stores = sorted(allocation.items(), key=lambda item: item[1], reverse=True)
        for store_id, qty in sorted_stores:
            remaining_capacity = await self._remaining_display_capacity(store_id, sku.category, db)
            qty = min(qty, max(remaining_capacity, 0))
            remaining_available = available_units - total_allocated
            qty = min(qty, max(remaining_available, 0))

            if qty > 0:
                constrained[store_id] = qty
                total_allocated += qty

            if total_allocated >= available_units:
                break

        return constrained

    async def get_available_for_first_allocation(self, grn_line: GRNLine, db: AsyncSession) -> int:
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
            .where(GRNLineReservation.grn_line_id == grn_line.id)
        )
        row = totals.one()
        reserved_sum = int(row.reserved_sum or 0)
        reservation_count = int(row.reservation_count or 0)

        if reservation_count == 0:
            reserved_sum = int(grn_line.ecom_reserved_qty or 0) + int(grn_line.ars_reserved_qty or 0)

        available = int(grn_line.units_received or 0) - reserved_sum
        return max(0, available)

    async def generate_reasoning(
        self,
        store_id: UUID,
        sku: SKU,
        qty: int,
        store_scores: dict[UUID, ScoreData],
        ros_data: dict[tuple[UUID, str], dict[str, float]],
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
        season_weeks_remaining = await self._season_weeks_remaining(sku, db)
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
