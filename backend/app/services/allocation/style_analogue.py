"""Style Analogue System — semantic demand inference for cold-start styles.

The category × price-band bridge gives every cold-start brand *something*,
but at category granularity it can't tell a kurta from a kurta. Two styles
in the same category and price band can sell at very different velocities;
collapsing them into a single bridge cell loses the per-style signal we
already have in last season's data.

This module restores style-level granularity by mapping each new (SS26)
style to its closest analogues in the prior season's catalogue, then
reading the analogues' per-store sales to infer expected demand.

Design choices:

  * **Deterministic, not learned.** We use a transparent weighted-similarity
    score the planner can audit. No embeddings, no opaque models — every
    match is explainable from the SKU attributes alone.
  * **Preloaded once per allocation.** The index is built at engine.generate
    time and queried purely from memory thereafter. No per-line SQL.
  * **Falls back gracefully.** When attributes are absent or no candidate
    clears the threshold, we return ``None`` and let the cascade try the
    next tier (cluster → bridge → grade → minimum).
  * **Explainable line-level.** Every line that uses analogue inference
    carries the matched style codes, scores, and a one-sentence narrative
    in ``ai_reasoning`` so the planner can audit the decision in the UI.

Cascade position: this module slots in **between store-history and
cluster-average**, the same place a brand with overlapping SKU codes would
have hit cluster-history. For cold-start brands (whose cluster-history is
empty by definition) it becomes the dominant signal.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SalesData, SKU


# ─── Scoring constants ──────────────────────────────────────────────────────

# Per-attribute weight in the final similarity score. The user's spec gives
# the high-level recipe (0.5 price + 0.3 attributes + 0.2 category); we keep
# that decomposition and let attribute_overlap split into its components.
PRICE_WEIGHT = 0.50
ATTRIBUTE_WEIGHT = 0.30
CATEGORY_WEIGHT = 0.20  # always 1.0 — guaranteed by candidate filter

# Candidate filter: prior style must share category and live within ±20% MRP
# of the new style. (When MRP is missing on either side, fall back to a
# price-band string match — same band = pass, different = fail.)
PRICE_BAND_TOLERANCE = 0.20

# Minimum score to *use* an analogue. Below this we don't trust the match
# enough to drive allocation; the cascade falls through.
MIN_SCORE_TO_USE = 0.45

# HIGH-confidence cutoff. Above 0.70 the match is strong enough that the
# planner can release at full quantity without manual override.
HIGH_CONFIDENCE_SCORE = 0.70

# Top-K analogues we consider when aggregating demand. More than 5 dilutes
# the signal; fewer than 3 is brittle if any one analogue is an outlier.
DEFAULT_TOP_K = 5
MIN_ANALOGUES_FOR_USE = 1  # accept even one strong analogue


# ─── Data classes ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StyleMeta:
    """Subset of SKU attributes needed for analogue matching. Frozen so
    instances can be cached / shared across stores without aliasing risk."""

    sku_id: UUID
    style_code: str
    category: str
    sub_category: str | None
    price_band: str | None
    mrp: float | None
    fabric: str | None
    colour_family: str | None
    risk_level: str | None


@dataclass
class AnalogueMatch:
    """One match between a new SKU and a prior style, plus the components
    of its similarity score so the UI can show *why* it matched."""

    style_code: str
    sku_id: UUID
    score: float
    price_similarity: float
    attribute_overlap: float
    category_match: float = 1.0  # always 1.0 by construction


@dataclass
class AnalogueDemandResult:
    """Inferred per-store weekly ROS for a new SKU, attributed to the prior
    styles that produced the inference. Returned by ``infer_demand``; the
    demand cascade either uses this (high-enough best score) or falls
    through to cluster-average."""

    weekly_ros: float
    matched_style_codes: list[str]
    scores: list[float]
    best_score: float
    confidence_tier: str  # "HIGH" | "MEDIUM"
    sample_size_weeks: int
    explanation: str


# ─── The index ──────────────────────────────────────────────────────────────


class StyleAnalogueIndex:
    """In-memory analogue resolver.

    Lifecycle:
      1. ``await index.load(db, brand_id)`` — pulls every SKU with sales
         history into a category-bucketed structure plus a flat
         ``(store_id, prior_sku_id) → weekly_ros`` map.
      2. ``index.find_analogues(new_sku)`` — returns top-K matches with
         scores. Cached per sku_id so cross-store calls are cheap.
      3. ``index.infer_demand(store_id, new_sku)`` — combines the analogues
         with that store's per-analogue ROS and returns an
         ``AnalogueDemandResult`` (or ``None`` if the score floor isn't met).
    """

    def __init__(self) -> None:
        self._candidates_by_category: dict[str, list[StyleMeta]] = defaultdict(list)
        self._store_style_ros: dict[tuple[UUID, UUID], float] = {}
        self._store_style_weeks: dict[tuple[UUID, UUID], int] = {}
        self._analogue_cache: dict[UUID, list[AnalogueMatch]] = {}
        self._loaded = False
        self._candidate_count = 0

    async def load(self, db: AsyncSession, brand_id: UUID) -> int:
        """Populate the index from the brand's SKU master + sales history.

        We only include SKUs that actually sold at least once — a SKU with
        no sales is useless as an analogue, and including it would let
        garbage candidates dilute the score floor.

        Returns the number of candidate styles indexed.
        """
        # 1) All SKUs with their attributes, indexed by category.
        sku_rows = (
            await db.execute(
                select(
                    SKU.id,
                    SKU.style_code,
                    SKU.category,
                    SKU.sub_category,
                    SKU.price_band,
                    SKU.mrp,
                    SKU.fabric,
                    SKU.colour_family,
                    SKU.resolved_risk_level,
                ).where(SKU.brand_id == brand_id)
            )
        ).all()

        sku_meta_by_id: dict[UUID, StyleMeta] = {}
        for row in sku_rows:
            cat = _normalize(row.category)
            if not cat:
                continue
            meta = StyleMeta(
                sku_id=row.id,
                style_code=str(row.style_code or "").strip(),
                category=cat,
                sub_category=_normalize(row.sub_category) or None,
                price_band=_normalize(row.price_band) or None,
                mrp=float(row.mrp) if row.mrp is not None else None,
                fabric=_normalize(row.fabric) or None,
                colour_family=_normalize(row.colour_family) or None,
                risk_level=_normalize(row.resolved_risk_level) or None,
            )
            sku_meta_by_id[row.id] = meta

        # 2) Per-(store, sku) weekly ROS — only for SKUs with at least one
        # week of positive sales. The aggregation is units / weeks observed
        # so the result survives synthetic-week spreading at ingestion.
        store_ros_rows = (
            await db.execute(
                select(
                    SalesData.store_id,
                    SalesData.sku_id,
                    func.sum(SalesData.units_sold).label("units"),
                    func.count(distinct(SalesData.week_start_date)).label("weeks"),
                )
                .where(
                    SalesData.brand_id == brand_id,
                    SalesData.units_sold > 0,
                )
                .group_by(SalesData.store_id, SalesData.sku_id)
            )
        ).all()

        skus_with_sales: set[UUID] = set()
        for row in store_ros_rows:
            weeks = int(row.weeks or 0)
            if weeks <= 0:
                continue
            ros = float(row.units or 0) / weeks
            if ros <= 0:
                continue
            self._store_style_ros[(row.store_id, row.sku_id)] = ros
            self._store_style_weeks[(row.store_id, row.sku_id)] = weeks
            skus_with_sales.add(row.sku_id)

        # 3) Bucket only SKUs that have sales — by category for fast lookup.
        for sku_id, meta in sku_meta_by_id.items():
            if sku_id not in skus_with_sales:
                continue
            self._candidates_by_category[meta.category].append(meta)
            self._candidate_count += 1

        self._loaded = True
        return self._candidate_count

    # ── Public API ─────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        return self._loaded and self._candidate_count > 0

    def find_analogues(
        self, new_sku: SKU, *, top_k: int = DEFAULT_TOP_K
    ) -> list[AnalogueMatch]:
        """Return the top-K analogues for ``new_sku``, sorted by descending
        score. Result is cached per ``sku_id`` so repeat lookups across the
        store loop are O(1).
        """
        if not self._loaded:
            return []

        cached = self._analogue_cache.get(new_sku.id)
        if cached is not None:
            return cached

        category = _normalize(new_sku.category)
        if not category:
            self._analogue_cache[new_sku.id] = []
            return []

        candidates = self._candidates_by_category.get(category, [])
        if not candidates:
            self._analogue_cache[new_sku.id] = []
            return []

        new_meta = StyleMeta(
            sku_id=new_sku.id,
            style_code=str(new_sku.style_code or "").strip(),
            category=category,
            sub_category=_normalize(new_sku.sub_category) or None,
            price_band=_normalize(new_sku.price_band) or None,
            mrp=float(new_sku.mrp) if new_sku.mrp is not None else None,
            fabric=_normalize(new_sku.fabric) or None,
            colour_family=_normalize(new_sku.colour_family) or None,
            risk_level=_normalize(new_sku.resolved_risk_level) or None,
        )

        scored: list[AnalogueMatch] = []
        for cand in candidates:
            # Don't match a SKU against itself.
            if cand.sku_id == new_sku.id:
                continue
            if not _passes_candidate_filter(new_meta, cand):
                continue
            price_sim = _price_similarity(new_meta, cand)
            attr_overlap = _attribute_overlap(new_meta, cand)
            score = (
                PRICE_WEIGHT * price_sim
                + ATTRIBUTE_WEIGHT * attr_overlap
                + CATEGORY_WEIGHT * 1.0
            )
            scored.append(
                AnalogueMatch(
                    style_code=cand.style_code,
                    sku_id=cand.sku_id,
                    score=round(score, 4),
                    price_similarity=round(price_sim, 4),
                    attribute_overlap=round(attr_overlap, 4),
                )
            )

        scored.sort(key=lambda m: m.score, reverse=True)
        top = [m for m in scored[:top_k] if m.score >= MIN_SCORE_TO_USE]
        self._analogue_cache[new_sku.id] = top
        return top

    def infer_demand(
        self,
        store_id: UUID,
        new_sku: SKU,
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> AnalogueDemandResult | None:
        """Compute per-store weekly ROS for ``new_sku`` from its analogues.

        The aggregation is a score-weighted average across analogues that
        actually sold *at this store*. We only count analogues with positive
        store-level history; a store that never sold any of the analogues
        returns ``None`` and the cascade falls through to cluster-average.
        """
        analogues = self.find_analogues(new_sku, top_k=top_k)
        if len(analogues) < MIN_ANALOGUES_FOR_USE:
            return None

        used: list[tuple[AnalogueMatch, float, int]] = []
        for match in analogues:
            ros = self._store_style_ros.get((store_id, match.sku_id))
            if ros is None or ros <= 0:
                continue
            weeks = self._store_style_weeks.get((store_id, match.sku_id), 0)
            used.append((match, ros, weeks))

        if not used:
            return None

        weight_total = sum(m.score for m, _, _ in used)
        if weight_total <= 0:
            return None

        weighted_ros = sum(score_ros * m.score for m, score_ros, _ in used) / weight_total
        weighted_ros = round(weighted_ros, 4)
        if weighted_ros <= 0:
            return None

        scores = [m.score for m, _, _ in used]
        best_score = max(scores)
        confidence = "HIGH" if best_score >= HIGH_CONFIDENCE_SCORE else "MEDIUM"
        sample_weeks = max(weeks for _, _, weeks in used)

        styles_str = ", ".join(m.style_code for m, _, _ in used[:3])
        more = f" (+{len(used) - 3} more)" if len(used) > 3 else ""
        explanation = (
            f"Demand inferred from {len(used)} similar SS-prior style"
            f"{'s' if len(used) != 1 else ''}: {styles_str}{more}. "
            f"They sold {weighted_ros:.1f} units/week at this store on average "
            f"(best match score {best_score:.2f})."
        )

        return AnalogueDemandResult(
            weekly_ros=weighted_ros,
            matched_style_codes=[m.style_code for m, _, _ in used],
            scores=[round(s, 4) for s in scores],
            best_score=round(best_score, 4),
            confidence_tier=confidence,
            sample_size_weeks=sample_weeks,
            explanation=explanation,
        )


# ─── Pure helpers (unit-testable without a DB) ──────────────────────────────


def _normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _passes_candidate_filter(new_meta: StyleMeta, cand: StyleMeta) -> bool:
    """Hard filter: same category, within price-band tolerance.

    Prefers MRP-based proximity when available on both sides, else falls
    back to exact price-band match. When neither side has band info we let
    the candidate through and rely on the score threshold to filter later.
    """
    if not new_meta.category or not cand.category:
        return False
    if new_meta.category != cand.category:
        return False
    if new_meta.mrp and cand.mrp and new_meta.mrp > 0 and cand.mrp > 0:
        ratio = abs(new_meta.mrp - cand.mrp) / max(new_meta.mrp, cand.mrp)
        return ratio <= PRICE_BAND_TOLERANCE
    if new_meta.price_band and cand.price_band:
        return new_meta.price_band == cand.price_band
    return True  # no band data on either side — allow, score will gate it


def _price_similarity(new_meta: StyleMeta, cand: StyleMeta) -> float:
    """1.0 = same price, decays linearly with relative MRP delta. Returns
    a neutral 0.5 when both sides lack price info — we don't want to
    falsely reward similarity we can't verify."""
    if new_meta.mrp and cand.mrp and new_meta.mrp > 0 and cand.mrp > 0:
        ratio = abs(new_meta.mrp - cand.mrp) / max(new_meta.mrp, cand.mrp)
        return max(0.0, 1.0 - ratio)
    if new_meta.price_band and cand.price_band:
        return 1.0 if new_meta.price_band == cand.price_band else 0.0
    return 0.5


def _attribute_overlap(new_meta: StyleMeta, cand: StyleMeta) -> float:
    """Fraction of comparable attributes that match.

    Comparable = both sides have a value. We deliberately don't penalize
    attributes that are missing from either side — retail data is messy and
    we'd rather score what we have than punish what we don't. When NO
    attribute is comparable we return 0.5 (neutral) so price + category
    drive the final score.
    """
    pairs = [
        (new_meta.fabric, cand.fabric),
        (new_meta.colour_family, cand.colour_family),
        (new_meta.sub_category, cand.sub_category),
        (new_meta.risk_level, cand.risk_level),
    ]
    available = 0
    matches = 0
    for left, right in pairs:
        if not left or not right:
            continue
        available += 1
        if left == right:
            matches += 1
    if available == 0:
        return 0.5
    return matches / available


# ─── Test-friendly factory ──────────────────────────────────────────────────


def build_index_from_meta(
    candidates: Iterable[StyleMeta],
    store_ros: dict[tuple[UUID, UUID], float] | None = None,
    store_weeks: dict[tuple[UUID, UUID], int] | None = None,
) -> StyleAnalogueIndex:
    """Construct an index without touching the DB. Used by unit tests so
    matching logic can be exercised in isolation."""
    idx = StyleAnalogueIndex()
    for meta in candidates:
        idx._candidates_by_category[meta.category].append(meta)
        idx._candidate_count += 1
    if store_ros:
        idx._store_style_ros.update(store_ros)
    if store_weeks:
        idx._store_style_weeks.update(store_weeks)
    idx._loaded = True
    return idx
