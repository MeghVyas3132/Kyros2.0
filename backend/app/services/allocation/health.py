from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from math import ceil
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AllocationLine, AllocationSession, GRNLine, SalesData, Season, SKU, Store


@dataclass
class HealthReport:
    score: int = 0
    label: str = "CRITICAL"
    sub_scores: Dict[str, float] = field(default_factory=dict)
    risks: List[Dict[str, Any]] = field(default_factory=list)
    top_recommendations: List[str] = field(default_factory=list)
    is_cold_start: bool = False
    season_week: int = 1
    line_diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_json(self):
        return {
            "score": self.score,
            "label": self.label,
            "sub_scores": self.sub_scores,
            "risks": self.risks,
            "top_recommendations": self.top_recommendations,
            "is_cold_start": self.is_cold_start,
            "season_week": self.season_week,
            "line_diagnostics": self.line_diagnostics,
        }

class AllocationHealthAnalyzer:
    """Computes Allocation Health, sub-score metrics, and risks based on v2 Design."""
    
    def __init__(self, session_id: UUID, brand_id: UUID, db: AsyncSession):
        self.session_id = session_id
        self.brand_id = brand_id
        self.db = db
        
        
    async def get_context(self) -> Dict[str, Any]:
        """Provides context on the season maturity and distribution for decision-making."""
        COLD_START_WEEKS_THRESHOLD = 4
        today = date.today()

        # Resolve season_id from the allocation session
        session_row = await self.db.scalar(
            select(AllocationSession).where(AllocationSession.id == self.session_id)
        )
        season_id = session_row.season_id if session_row else None

        # Defaults if no season is linked
        if season_id is None:
            return {
                "is_cold_start": True,
                "season_week": 1,
                "total_season_weeks": 16,
                "weeks_remaining": 8,
                "demand_confidence_mix": {"historical": 0.0, "dna": 0.8},
            }

        season = await self.db.scalar(
            select(Season).where(Season.id == season_id, Season.brand_id == self.brand_id)
        )
        if season is None:
            return {
                "is_cold_start": True,
                "season_week": 1,
                "total_season_weeks": 16,
                "weeks_remaining": 8,
                "demand_confidence_mix": {"historical": 0.0, "dna": 0.8},
            }

        # Calculate season_week and total_season_weeks
        total_season_days = max((season.end_date - season.start_date).days, 1)
        total_season_weeks = max(ceil(total_season_days / 7), 1)

        elapsed_days = max((today - season.start_date).days, 0)
        season_week = min(elapsed_days // 7 + 1, total_season_weeks)

        remaining_days = max((season.end_date - today).days, 0)
        weeks_remaining = max(ceil(remaining_days / 7), 1) if remaining_days > 0 else 1

        # Count distinct weeks of sales_data for this brand within the season window
        distinct_sales_weeks = await self.db.scalar(
            select(func.count(distinct(SalesData.week_start_date))).where(
                SalesData.brand_id == self.brand_id,
                SalesData.week_start_date >= season.start_date,
                SalesData.week_start_date <= season.end_date,
                SalesData.sku_id.in_(
                    select(GRNLine.sku_id).where(GRNLine.grn_id == session_row.grn_id)
                )
            )
        ) or 0

        is_cold_start = int(distinct_sales_weeks) < COLD_START_WEEKS_THRESHOLD

        # Confidence mix: more historical data → higher historical weight
        if distinct_sales_weeks >= 8:
            hist_weight, dna_weight = 0.8, 0.2
        elif distinct_sales_weeks >= COLD_START_WEEKS_THRESHOLD:
            hist_weight, dna_weight = 0.5, 0.5
        else:
            hist_weight, dna_weight = 0.0, 0.8

        return {
            "is_cold_start": is_cold_start,
            "season_week": season_week,
            "total_season_weeks": total_season_weeks,
            "weeks_remaining": weeks_remaining,
            "demand_confidence_mix": {
                "historical": hist_weight,
                "dna": dna_weight,
            },
        }
    
    async def analyze(self) -> HealthReport:
        # Load all needed data
        # We will stream the non-zero lines and zero lines that had demand
        stmt = select(
            AllocationLine.store_id,
            AllocationLine.sku_id,
            AllocationLine.ai_recommended_qty,
            AllocationLine.final_qty,
            AllocationLine.ai_reasoning,
            AllocationLine.ai_projections,
            AllocationLine.ai_confidence
        ).where(AllocationLine.session_id == self.session_id)

        result = await self.db.execute(stmt)
        lines = result.all()  # Depending on volume, might need chunking in production
        line_diagnostics = await self._compute_line_diagnostics(lines)

        # 1. Evaluate Metrics
        coverage_metrics = self._compute_coverage(lines)
        alignment_metrics = self._compute_alignment(lines)
        balance_metrics = self._compute_balance(lines)
        presentation_metrics = self._compute_presentation(lines)
        confidence_metrics = self._compute_confidence(lines)
        
        # 2. Score Computation Base
        WEIGHTS = {
            "coverage": 0.30,
            "demand_align": 0.25,
            "confidence": 0.20,
            "presentation": 0.15,
            "balance": 0.10,
        }
        
        sub_scores = {
            "coverage": coverage_metrics["score"],
            "demand_align": alignment_metrics["score"],
            "balance": balance_metrics["score"],
            "presentation": presentation_metrics["score"],
            "confidence": confidence_metrics["score"],
        }
        
        base_score = sum(WEIGHTS[m] * sub_scores[m] for m in WEIGHTS)

        # 3. Detect Risks
        # Will expand this
        risks = []

        # 4. Hard Penalties — calibrated against the signal grade. A cold-start
        # brand running off the category-bridge legitimately spreads thin and
        # should NOT be tarred with the same brush as a brand that has full
        # store-history but chose to allocate poorly.
        signal_grade = line_diagnostics.get("signal_grade", "MEDIUM")
        final_score, penalties = self._apply_hard_penalties(
            base_score,
            coverage_metrics,
            presentation_metrics,
            lines,
            signal_grade=signal_grade,
        )
        for p in penalties:
            risks.append({"type": "HARD_PENALTY", "severity": "CRITICAL", "explanation": p})
            
        final_score = max(0, min(100, int(final_score)))
        
        # 5. Determine Label
        if final_score >= 75:
            label = "SAFE"
        elif final_score >= 55:
            label = "CAUTION"
        elif final_score >= 35:
            label = "RISKY"
        else:
            label = "CRITICAL"
        context = await self.get_context()
        recommendations_sys = generate_recommendations(risks, coverage_metrics, context)
        
        return HealthReport(
            score=final_score,
            label=label,
            sub_scores=sub_scores,
            risks=risks,
            top_recommendations=[r["action"] for r in recommendations_sys],
            is_cold_start=context.get("is_cold_start", False),
            season_week=context.get("season_week", 1),
            line_diagnostics=line_diagnostics,
        )
        
    async def _compute_line_diagnostics(self, lines) -> Dict[str, Any]:
        """One-pass aggregation across all allocation lines that the verdict
        layer consumes. Kept distinct from the sub-score calcs so the latter
        can stay narrow while this can grow over time.

        We also probe two cross-table facts:
          * total_active_stores (cap on coverage)
          * sku_overlap_with_sales_pct (the cold-start canary)
        """
        from collections import Counter

        ros_source_counts: Counter = Counter()
        confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        total_units = 0
        positive_lines = 0
        store_ids: set = set()

        for row in lines:
            qty = int(row.final_qty or row.ai_recommended_qty or 0)
            reasoning = row.ai_reasoning or {}
            source = reasoning.get("ros_source") or "unknown"
            ros_source_counts[source] += 1

            if qty <= 0:
                continue
            positive_lines += 1
            total_units += qty
            store_ids.add(row.store_id)
            tier = (row.ai_confidence or "LOW").upper()
            if tier not in confidence_counts:
                tier = "LOW"
            confidence_counts[tier] += 1

        # GRN total receipt — the denominator for fill ratio.
        session_row = await self.db.scalar(
            select(AllocationSession).where(AllocationSession.id == self.session_id)
        )
        received_units = 0
        sku_overlap_pct = None
        if session_row and session_row.grn_id:
            received_units = int(
                await self.db.scalar(
                    select(func.coalesce(func.sum(GRNLine.units_received), 0)).where(
                        GRNLine.grn_id == session_row.grn_id
                    )
                )
                or 0
            )
            grn_skus = (
                await self.db.execute(
                    select(GRNLine.sku_id).where(GRNLine.grn_id == session_row.grn_id)
                )
            ).all()
            grn_sku_ids = {row[0] for row in grn_skus}
            if grn_sku_ids:
                hits = (
                    await self.db.scalar(
                        select(func.count(distinct(SalesData.sku_id))).where(
                            SalesData.brand_id == self.brand_id,
                            SalesData.sku_id.in_(grn_sku_ids),
                        )
                    )
                    or 0
                )
                sku_overlap_pct = round(hits / max(len(grn_sku_ids), 1), 3)

        # Active store count — the denominator for "stores receiving".
        total_active_stores = (
            await self.db.scalar(
                select(func.count(Store.id)).where(
                    Store.brand_id == self.brand_id,
                    Store.is_active.is_(True),
                )
            )
            or 0
        )

        # Source classification — drives both penalty calibration and the
        # DATA-vs-STRATEGY failure classification.
        # ``style_analogue`` is treated as STRONG when it fires: it's
        # per-store, per-style inference (not category-averaged), so a
        # brand running primarily on analogues gets the same calibration
        # confidence as one running on direct store-historical signal.
        STRONG_SOURCES = {"store_historical", "cluster_average", "style_analogue"}
        MEDIUM_SOURCES = {"category_bridge", "grade_average"}
        WEAK_SOURCES = {"minimum_presentation", "fallback", "style_dna_analogue"}

        total_lines = sum(ros_source_counts.values()) or 1
        strong_lines = sum(c for s, c in ros_source_counts.items() if s in STRONG_SOURCES)
        medium_lines = sum(c for s, c in ros_source_counts.items() if s in MEDIUM_SOURCES)
        weak_lines = sum(c for s, c in ros_source_counts.items() if s in WEAK_SOURCES)

        strong_ratio = round(strong_lines / total_lines, 4)
        medium_ratio = round(medium_lines / total_lines, 4)
        weak_ratio = round(weak_lines / total_lines, 4)

        # Signal grade — answers "how good was the demand signal we used?"
        # HIGH    → most lines used real per-SKU history
        # MEDIUM  → most lines used the category bridge (per-store, cross-SKU)
        # LOW     → most lines fell to minimum-presentation / DNA analogue
        if strong_ratio >= 0.5:
            signal_grade = "HIGH"
        elif strong_ratio + medium_ratio >= 0.5:
            signal_grade = "MEDIUM"
        else:
            signal_grade = "LOW"

        return {
            "total_lines": total_lines,
            "positive_lines": positive_lines,
            "allocated_units": total_units,
            "received_units": int(received_units),
            "alloc_to_received_ratio": (
                round(total_units / received_units, 4) if received_units > 0 else 0.0
            ),
            "high_confidence_lines": confidence_counts["HIGH"],
            "moderate_confidence_lines": confidence_counts["MEDIUM"],
            "low_confidence_lines": confidence_counts["LOW"],
            "demand_source_breakdown": dict(ros_source_counts),
            "fallback_demand_ratio": weak_ratio,
            "strong_demand_ratio": strong_ratio,
            "medium_demand_ratio": medium_ratio,
            "signal_grade": signal_grade,
            "distinct_stores_with_allocation": len(store_ids),
            "total_active_stores": int(total_active_stores),
            "sku_overlap_with_sales_pct": sku_overlap_pct,
        }

    def _compute_coverage(self, lines) -> Dict[str, Any]:
        healthy = 0
        lean = 0
        overstock = 0
        stockout = 0
        dead = 0
        total = 0
        
        for row in lines:
            # Skip lines the engine never intended to allocate
            if (row.ai_recommended_qty or 0) == 0 and (row.final_qty or 0) == 0:
                continue
            reasoning = row.ai_reasoning or {}
            ros = reasoning.get("weekly_ros", 0)
            if ros <= 0:
                continue
            
            # Skip fallback for coverage calc
            if reasoning.get("ros_source") == "minimum_presentation":
                continue
                
            qty = row.final_qty or 0
            cover = qty / ros
            
            total += 1
            if cover < 2:
                stockout += 1
            elif cover < 4:
                lean += 1
            elif cover <= 8:
                healthy += 1
            elif cover <= 12:
                overstock += 1
            else:
                dead += 1
                
        if total == 0:
            return {"score": 50.0, "total": 0}
            
        score = (
            (healthy / total) * 1.0 +
            (lean / total) * 0.6 +
            (overstock / total) * 0.4
        ) * 100
        
        return {
            "score": score,
            "pct_stockout": stockout / total,
            "total": total
        }

    def _compute_alignment(self, lines) -> Dict[str, Any]:
        aligned = 0
        severely_under = 0
        total = 0
        for row in lines:
            # Skip lines the engine never intended to allocate
            if (row.ai_recommended_qty or 0) == 0 and (row.final_qty or 0) == 0:
                continue
            # Only evaluate lines that had actual demand (not just fallback 0s)
            proj = row.ai_projections or {}
            raw_demand = proj.get("total_demand_before_cap", 0)
            if raw_demand <= 0:
                continue
            ratio = row.final_qty / raw_demand if raw_demand > 0 else 0
            if ratio < 0.3:
                severely_under += 1
            elif 0.7 <= ratio <= 1.2:
                aligned += 1
            total += 1
        
        if total == 0:
            return {"score": 50.0, "pct_aligned": 0.0, "pct_severely_under": 0.0}
        score = max(0, (aligned / total) * 100 - (severely_under / total) * 30)
        return {"score": score, "pct_aligned": aligned/total, "pct_severely_under": severely_under/total}

    def _compute_balance(self, lines) -> Dict[str, Any]:
        # Simplify balance by looking at spread across stores
        from collections import defaultdict
        store_qty = defaultdict(int)
        for row in lines:
            store_qty[row.store_id] += row.final_qty
            
        qtys = sorted(store_qty.values(), reverse=True)
        if not qtys:
            return {"score": 50.0}
            
        total_qty = sum(qtys)
        top5_pct = sum(qtys[:5]) / total_qty if total_qty > 0 else 0
        
        # Simple skew threshold scoring
        if top5_pct < 0.4:
            score = 100
        elif top5_pct < 0.6:
            score = 70
        else:
            score = 30
            
        return {"score": score, "top5_pct": top5_pct}
        
    def _compute_presentation(self, lines) -> Dict[str, Any]:
        from collections import defaultdict
        # Map store -> total units (since lines lacks style_id directly, store total is a good proxy for overall depth)
        # A more precise way is to use sku_id grouped by style, but style_code is in SKUs table.
        # We will approximate depth by grouping by (store_id, string_prefix_of_sku) or just store_id
        store_style_qty = defaultdict(int)
        for row in lines:
            if row.final_qty > 0:
                # We can group by store_id and ai_reasoning's narrative cap if possible, or just assume sku_id prefix is style
                # Actually, engine outputs style-level ai_projections!
                store_style_qty[row.store_id] += row.final_qty
                
        thin = 0
        marginal = 0
        adequate = 0
        for qty in store_style_qty.values():
            if qty <= 2:
                thin += 1
            elif qty <= 4:
                marginal += 1
            else:
                adequate += 1
                
        total = len(store_style_qty)
        if total == 0:
            return {"score": 50.0, "pct_thin": 0.0}
            
        score = ((adequate/total)*1.0 + (marginal/total)*0.5) * 100
        return {"score": score, "pct_thin": thin/total}
        
    def _compute_confidence(self, lines) -> Dict[str, Any]:
        high, med, low = 0, 0, 0
        total = 0
        for row in lines:
            # We only care about confidence for lines we actually allocated
            if row.final_qty > 0:
                c = row.ai_confidence or "LOW"
                if c == "HIGH": high += 1
                elif c == "MEDIUM": med += 1
                else: low += 1
                total += 1
                
        if total == 0:
            return {"score": 50.0}
        
        score = ((high/total)*1.0 + (med/total)*0.6 + (low/total)*0.2) * 100
        return {"score": score, "pct_low": low/total}

    def _apply_hard_penalties(
        self,
        base_score,
        cov_m,
        pres_m,
        lines,
        *,
        signal_grade: str = "MEDIUM",
    ) -> tuple[float, List[str]]:
        """Apply stockout + thin-allocation penalties, calibrated by signal
        grade. The original calibration assumed ``store_historical`` was the
        dominant tier; under that assumption a thin allocation is a planner
        mistake worth a 15-point hit. With ``category_bridge`` dominant
        (cold-start brand) thin spread is the *expected* shape — penalize
        more lightly so the verdict lands in CAUTION instead of REJECT.

        Penalty caps:
          HIGH  signal: stockout up to 20, thin up to 15  (original)
          MED   signal: stockout up to 12, thin up to  8  (cold-start aware)
          LOW   signal: stockout up to  6, thin up to  4  (data is the real
                                                           problem; depth
                                                           tuning is moot)
        """
        score = base_score
        penalties: List[str] = []

        if signal_grade == "HIGH":
            stockout_cap, thin_cap = 20, 15
        elif signal_grade == "MEDIUM":
            stockout_cap, thin_cap = 12, 8
        else:
            stockout_cap, thin_cap = 6, 4

        # P1: Stockout risk
        if cov_m.get("pct_stockout", 0) > 0.15:
            penalty = min(stockout_cap, int(cov_m["pct_stockout"] * 50))
            score -= penalty
            penalties.append(f"-{penalty} pts: High stockout risk")

        # P2: Thin allocation
        pct_thin = pres_m.get("pct_thin", 0)
        if pct_thin > 0.40:
            penalty = min(thin_cap, int((pct_thin - 0.40) * 50))
            score -= penalty
            penalties.append(
                f"-{penalty} pts: {pct_thin*100:.0f}% of allocations are un-sellably thin"
            )

        return score, penalties

def compute_decision(
    health_score: int,
    risks: List[Dict[str, Any]],
    context: Dict[str, Any],
    sub_scores: Dict[str, float] | None = None,
    line_diagnostics: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the planner-facing verdict.

    On top of the verdict + health score, we add a single ``blocked_reason``
    and ``fix`` line so the UI never has to ask the planner to interpret
    sub-scores. The reason is derived in priority order from the worst
    metric we can defensibly attribute. ``line_diagnostics`` carries the
    aggregated demand-source / allocated-vs-received facts the
    ``AllocationHealthAnalyzer`` already had to compute — we reuse them
    here instead of re-querying.
    """
    if health_score >= 75:
        verdict = "APPROVE"
        action = "Safe to release. All metrics within acceptable range."
    elif health_score >= 55:
        verdict = "APPROVE_WITH_CAUTION"
        action = "Release to Tier 1-2 stores. Hold remainder centrally for Week 2 re-run."
    elif health_score >= 35:
        verdict = "REVIEW_REQUIRED"
        action = "Do not release. Manual override or strategy change required."
    else:
        verdict = "REJECT"
        action = "CRITICAL FAIL. Inventory too thin to sell. Change depth strategy."

    reasons = [r.get("explanation", r.get("type")) for r in risks[:3]]

    blocked_reason, fix, failure_class = _explain_block(
        verdict=verdict,
        sub_scores=sub_scores or {},
        line_diagnostics=line_diagnostics or {},
        context=context,
    )

    # Verdict softening for "Case B" runs: when the failure is clearly a
    # STRATEGY problem (signal is real, plan is wrong), don't shout REJECT
    # at the planner — that's the right verdict for missing data, not for a
    # well-engined plan whose inputs are off. Bump REJECT (≤34) up to
    # REVIEW_REQUIRED so the planner sees an actionable amber, and bump
    # REVIEW_REQUIRED with strong signal up to APPROVE_WITH_CAUTION.
    diag = line_diagnostics or {}
    signal_grade = str(diag.get("signal_grade") or "LOW")
    if failure_class == "STRATEGY" and signal_grade in {"HIGH", "MEDIUM"}:
        if verdict == "REJECT":
            verdict = "REVIEW_REQUIRED"
            action = (
                "Strategy adjustment required. Engine's signal is healthy — the buy plan "
                "or store-group footprint needs tightening before approving."
            )
        elif verdict == "REVIEW_REQUIRED" and signal_grade == "HIGH":
            verdict = "APPROVE_WITH_CAUTION"
            action = (
                "Release to Tier 1-2 stores; hold remainder centrally and re-run after "
                "Week 1 sell-through to validate the depth call."
            )

    return {
        "verdict": verdict,
        "health_score": health_score,
        "why": reasons,
        "action": action,
        "hold_recommendation": 30 if verdict == "APPROVE_WITH_CAUTION" else 0,
        "blocked_reason": blocked_reason,
        "fix": fix,
        "failure_class": failure_class,
        "line_diagnostics": diag,
    }


def _explain_block(
    *,
    verdict: str,
    sub_scores: Dict[str, float],
    line_diagnostics: Dict[str, Any],
    context: Dict[str, Any],
) -> tuple[str | None, str | None, str]:
    """Translate sub-scores + line diagnostics into a one-sentence blocker,
    a one-sentence fix, and a failure-class label.

    Returns ``(reason, fix, failure_class)`` where ``failure_class`` is one of:
      * ``DATA_QUALITY`` — engine couldn't trust its inputs (no overlap,
        too much fallback). Fix is upstream: better data.
      * ``STRATEGY``     — engine had usable signal but the buy plan or
        distribution shape is wrong (too thin, too few stores, etc).
        Fix is in the planner's hands.
      * ``ELIGIBILITY``  — engine had signal but most stores got filtered
        out by store-group / climate / grade rules.
      * ``NONE``         — nothing's blocking; verdict is APPROVE-band.

    Priority order is bottom-up: data problems beat strategy problems beat
    presentation problems. The planner can't fix presentation if the data
    isn't there, and they can't fix data if every store is excluded — so we
    surface the layer that has to be fixed first.
    """
    if verdict in {"APPROVE", "APPROVE_WITH_CAUTION"}:
        return None, None, "NONE"

    fill = float(line_diagnostics.get("alloc_to_received_ratio") or 0.0)
    high_conf = int(line_diagnostics.get("high_confidence_lines", 0))
    moderate_conf = int(line_diagnostics.get("moderate_confidence_lines", 0))
    low_conf = int(line_diagnostics.get("low_confidence_lines", 0))
    fallback_ratio = float(line_diagnostics.get("fallback_demand_ratio") or 0.0)
    medium_ratio = float(line_diagnostics.get("medium_demand_ratio") or 0.0)
    strong_ratio = float(line_diagnostics.get("strong_demand_ratio") or 0.0)
    signal_grade = str(line_diagnostics.get("signal_grade") or "LOW")
    sku_overlap_pct = line_diagnostics.get("sku_overlap_with_sales_pct")  # may be None
    distinct_stores_with_alloc = int(line_diagnostics.get("distinct_stores_with_allocation", 0))
    total_stores = int(line_diagnostics.get("total_active_stores", 0))

    demand_align = float(sub_scores.get("demand_align", 50.0))
    confidence = float(sub_scores.get("confidence", 50.0))
    coverage = float(sub_scores.get("coverage", 50.0))
    presentation = float(sub_scores.get("presentation", 50.0))

    # ── DATA_QUALITY tier ─────────────────────────────────────────────────

    # 1. No demand signal at all — the cold-start trap.
    if demand_align <= 5 and (high_conf + moderate_conf) == 0 and low_conf > 0:
        if sku_overlap_pct is not None and sku_overlap_pct < 0.05:
            return (
                "Allocation blocked because the buy file styles have no overlap with sales history. "
                "Engine had no defensible demand signal for any SKU.",
                "Re-upload sales using the same style codes as the buy file, OR provide a "
                "category × price-band analogue map so the engine can bridge demand "
                "from comparable styles.",
                "DATA_QUALITY",
            )
        return (
            "Allocation blocked because no historical demand signal could be attached "
            "to the GRN's SKUs.",
            "Confirm sales history covers the same styles (or analogues) as the buy file, "
            "then re-run.",
            "DATA_QUALITY",
        )

    # 2. Most lines fell to the fallback tier — engine had to make it up.
    if fallback_ratio >= 0.7 and signal_grade == "LOW":
        return (
            f"Allocation built — {fallback_ratio * 100:.0f}% of lines used the "
            "minimum-presentation fallback because no per-store demand was found.",
            "Provide more weeks of sales history or load a category × price-band "
            "analogue file so the engine stops falling back.",
            "DATA_QUALITY",
        )

    # ── ELIGIBILITY tier ─────────────────────────────────────────────────

    # 3. Engine ran but only a handful of stores received anything.
    if total_stores > 0 and distinct_stores_with_alloc <= max(1, int(total_stores * 0.05)):
        return (
            f"Allocation blocked: only {distinct_stores_with_alloc} of "
            f"{total_stores} active stores received any inventory.",
            "Most stores were excluded by store-group rule, climate zone, or grade. "
            "Loosen one of these or update the buy plan's store-group rule.",
            "ELIGIBILITY",
        )

    # ── STRATEGY tier (signal is OK — the plan is the problem) ───────────

    # 4a. Demand exceeds supply. The engine wanted to send more than the
    # GRN had, so most lines are clipped to a fraction of intended depth.
    # demand_align measures "did we send what we intended?" — when it tanks
    # while signal is healthy, the buy quantity itself was too small.
    if demand_align < 35 and (strong_ratio + medium_ratio) >= 0.5 and fill < 0.85:
        return (
            "Buy plan is undersized for the network's demand — engine wanted to ship more "
            "than the GRN had, so most stores got a fraction of their intended depth.",
            "Increase total buy quantity for the top-volume styles, OR reduce the number "
            "of stores in the buy plan's store-group rule. Same data, smaller distribution "
            "footprint will produce a healthy plan.",
            "STRATEGY",
        )

    # 4b. Allocation is too thin per store while signal is real.
    # Triggered for the cold-start-bridge-dominant case where presentation
    # tanks because the buy plan was sized for fewer stores than the
    # network actually has.
    if presentation < 50 and (strong_ratio + medium_ratio) >= 0.5:
        return (
            f"Buy plan is too thin to spread across the network — most "
            f"(store × style) cells receive 1–2 units, below sellable depth. "
            f"Signal is real ({signal_grade.lower()} grade) but depth is wrong.",
            "Reduce the number of stores in the buy plan's store-group rule, OR "
            "increase per-style buy depth, OR drop the long-tail styles. "
            "Re-run and the same engine + same data will produce a healthy plan.",
            "STRATEGY",
        )

    # 5. Coverage is bad but signal is OK — too few weeks of cover.
    if coverage < 35 and demand_align >= 40:
        return (
            "Allocation has signal but depth is unhealthy — too many stores will stock out "
            "before Week 4.",
            "Increase opening-order percentage or reduce the number of stores in the buy "
            "plan's store-group rule.",
            "STRATEGY",
        )

    # 6. Catch-all thin presentation (signal grade unknown / weak).
    if presentation < 35:
        return (
            "Allocation is too thin per store — most stores receive un-sellable depth.",
            "Activate the minimum-viable-allocation rule (≥3 units/store) under "
            "depth_first strategy.",
            "STRATEGY",
        )

    # 7. Engine ran but nothing meaningful was distributed (and it's not
    # eligibility — handled in #3 above).
    if fill < 0.10:
        return (
            f"Allocation blocked: only {fill * 100:.1f}% of received units could be "
            "responsibly distributed.",
            "Either widen the demand signal (sales mapping / analogue file) or accept "
            "a partial release and re-run after Week 1 sell-through.",
            "DATA_QUALITY",
        )

    # Generic fallback — should rarely fire because the rules above cover most cases.
    return (
        "Allocation needs review — one or more health metrics are below the release threshold.",
        "Inspect the sub-scores and the exceptions table; override or adjust strategy "
        "before approving.",
        "STRATEGY",
    )

def generate_recommendations(risks: List[Dict[str, Any]], metrics: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    recs = []
    
    for risk in risks:
        if risk["type"] == "HARD_PENALTY" and "thin" in risk.get("explanation", ""):
            recs.append({
                "priority": 1,
                "action": "Activate MVA enforcement (min 3 units/store) under depth_first strategy",
                "impact": "Eliminates thin allocations, ensuring stores can actually display stock",
            })
        elif risk["type"] == "HARD_PENALTY" and "stockout" in risk.get("explanation", ""):
            recs.append({
                "priority": 2,
                "action": "Increase buffer for Tier 1 stores",
                "impact": "Prevents immediate stockouts at top volume doors",
            })
            
    # Default recs if empty
    if not recs:
        recs.append({
            "priority": 3,
            "action": "Monitor sell-through in Week 1-2",
            "impact": "Validates DNA analogue matching for new styles",
        })
        
    recs.sort(key=lambda x: x["priority"])
    return recs
