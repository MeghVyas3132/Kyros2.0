"""Analogue → Decision Layer.

The allocation engine answers *"what is happening?"* — line-by-line: how
many units of each SKU go to which store, why, with what confidence. The
decision layer answers *"what should I do?"* — at portfolio level, in 3-5
prioritized business actions a VP can act on without reading a single
metric tile.

Design rules (enforced by the spec):

  * No dashboards, no raw analytics views, no internal weights.
  * 3-5 actions max. We rank by impact and truncate the long tail.
  * Portfolio-level — never per-line. The line-level signal feeds the
    aggregator; the aggregator drives the rules; the rules emit actions.
  * Every action carries (a) a one-sentence headline, (b) a body, (c) an
    impact tier, (d) a confidence tier, and (e) one line of data backing
    so the planner can audit the recommendation.
  * Every run gets classified: ``DATA`` (fix inputs), ``STRATEGY`` (fix
    the plan), or ``HEALTHY`` (release).

The module reads everything it needs from the persisted ``health_report``
+ ``decision`` JSON on the AllocationSession (computed by the existing
intelligence layer) plus a single per-style aggregation query against
``allocation_lines``. No new schema, no new persistence — the decision
summary is recomputed on demand each time the endpoint is hit.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AllocationLine, AllocationSession, SKU


# ─── Output dataclasses ────────────────────────────────────────────────────


@dataclass
class Action:
    """One recommended business action.

    ``id`` is stable across runs (e.g. ``REDUCE_DISTRIBUTION``) so the
    frontend can attach behaviour without parsing the title. ``category``
    groups actions for the UI ("Depth", "Distribution", "Buy plan", etc).
    """

    id: str
    category: str
    title: str
    description: str
    impact: str  # "HIGH" | "MEDIUM" | "LOW"
    confidence: str  # "HIGH" | "MEDIUM" | "LOW"
    data_backing: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionSummary:
    """Top-level payload returned to the API. Everything a VP needs to see
    on first paint: classification, headline summary, ranked actions, and
    the raw aggregates that backed them (so a curious planner can dig)."""

    classification: str  # "DATA" | "STRATEGY" | "HEALTHY"
    summary: str
    actions: list[Action]
    aggregates: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "summary": self.summary,
            "actions": [a.to_dict() for a in self.actions],
            "aggregates": self.aggregates,
        }


# ─── Internal context (passed to each rule) ────────────────────────────────


@dataclass
class _DecisionContext:
    """Aggregated, immutable snapshot of one allocation. All rules read from
    this — nobody hits the DB during rule evaluation."""

    session_id: UUID
    brand_id: UUID
    verdict: str  # "APPROVE" | "APPROVE_WITH_CAUTION" | "REVIEW_REQUIRED" | "REJECT"
    failure_class: str  # "DATA_QUALITY" | "STRATEGY" | "ELIGIBILITY" | "NONE"
    health_score: int

    # Demand source distribution (from line_diagnostics)
    pct_store_history: float
    pct_style_analogue: float
    pct_category_bridge: float
    pct_grade: float
    pct_minimum: float
    signal_grade: str  # "HIGH" | "MEDIUM" | "LOW"

    # Confidence distribution
    pct_confidence_high: float
    pct_confidence_medium: float
    pct_confidence_low: float

    # Allocation health
    allocated_units: int
    received_units: int
    fill_ratio: float
    distinct_stores_with_alloc: int
    total_active_stores: int
    avg_units_per_store_style: float

    # Sub-scores
    sub_scores: dict[str, float]

    # Per-style breakdown (top N by allocated units, with analogue scores)
    top_styles: list[dict[str, Any]] = field(default_factory=list)
    weak_analogue_styles: list[dict[str, Any]] = field(default_factory=list)
    strong_analogue_styles: list[dict[str, Any]] = field(default_factory=list)

    # Pre-computed counts for rule triggers
    distinct_styles_allocated: int = 0


# ─── Public API ────────────────────────────────────────────────────────────


async def build_decision_summary(
    session_id: UUID, brand_id: UUID, db: AsyncSession
) -> DecisionSummary:
    """Read an allocation session and return a portfolio-level decision pack.

    Raises ``ValueError`` if the session has no health_report yet (i.e.
    the intelligence layer hasn't run for this session). The HTTP layer
    converts that to 409.
    """
    session = await db.get(AllocationSession, session_id)
    if session is None or session.brand_id != brand_id:
        raise ValueError("Allocation session not found")

    if not session.health_report:
        raise ValueError(
            "Allocation has no health report yet — wait for generation to finish."
        )

    ctx = await _build_context(session, db)
    actions = _run_rule_pipeline(ctx)
    actions = _rank_and_truncate(actions, max_actions=5)
    classification = _classify(ctx)
    summary = _build_summary(ctx, classification, actions)

    return DecisionSummary(
        classification=classification,
        summary=summary,
        actions=actions,
        aggregates={
            "verdict": ctx.verdict,
            "failure_class": ctx.failure_class,
            "health_score": ctx.health_score,
            "signal_grade": ctx.signal_grade,
            "fill_ratio": round(ctx.fill_ratio, 3),
            "stores_receiving": ctx.distinct_stores_with_alloc,
            "total_active_stores": ctx.total_active_stores,
            "distinct_styles_allocated": ctx.distinct_styles_allocated,
            "avg_units_per_store_style": round(ctx.avg_units_per_store_style, 2),
            "demand_source_breakdown": {
                "store_history": round(ctx.pct_store_history, 3),
                "style_analogue": round(ctx.pct_style_analogue, 3),
                "category_bridge": round(ctx.pct_category_bridge, 3),
                "grade": round(ctx.pct_grade, 3),
                "minimum": round(ctx.pct_minimum, 3),
            },
            "confidence_breakdown": {
                "high": round(ctx.pct_confidence_high, 3),
                "medium": round(ctx.pct_confidence_medium, 3),
                "low": round(ctx.pct_confidence_low, 3),
            },
            "top_styles": ctx.top_styles[:10],
        },
    )


# ─── Context build (the only DB-touching code in this module) ─────────────


async def _build_context(session: AllocationSession, db: AsyncSession) -> _DecisionContext:
    health_report = session.health_report or {}
    decision = session.decision or {}
    sub_scores = dict(health_report.get("sub_scores") or {})
    diag = dict(health_report.get("line_diagnostics") or decision.get("line_diagnostics") or {})

    total_lines = max(int(diag.get("total_lines") or 1), 1)
    breakdown = dict(diag.get("demand_source_breakdown") or {})

    def _pct(*keys: str) -> float:
        return sum(int(breakdown.get(k, 0)) for k in keys) / total_lines

    pct_store_history = _pct("store_historical")
    pct_style_analogue = _pct("style_analogue")
    pct_category_bridge = _pct("category_bridge", "cluster_average")
    pct_grade = _pct("grade_average")
    pct_minimum = _pct("minimum_presentation", "fallback", "style_dna_analogue")

    pos_lines = max(int(diag.get("positive_lines") or 0), 0)
    high_conf = int(diag.get("high_confidence_lines") or 0)
    med_conf = int(diag.get("moderate_confidence_lines") or 0)
    low_conf = int(diag.get("low_confidence_lines") or 0)
    conf_total = max(high_conf + med_conf + low_conf, 1)

    allocated_units = int(diag.get("allocated_units") or 0)
    received_units = int(diag.get("received_units") or 0)
    fill_ratio = float(diag.get("alloc_to_received_ratio") or 0.0)

    distinct_stores = int(diag.get("distinct_stores_with_allocation") or 0)
    total_active = int(diag.get("total_active_stores") or 0)

    # Per-style aggregation. We pull (style_code, total_units, max_score,
    # avg_score, line_count) in one query so the rules can pick top-N and
    # spot weak/strong analogues without a per-line scan.
    style_rows = await _aggregate_per_style(session.id, session.brand_id, db)
    top_styles = sorted(style_rows, key=lambda r: r["allocated_units"], reverse=True)[:10]

    strong_analogue_styles = [
        r for r in style_rows
        if r.get("source") == "style_analogue"
        and r.get("best_analogue_score") is not None
        and float(r["best_analogue_score"]) >= 0.75
    ]
    weak_analogue_styles = [
        r for r in style_rows
        if r.get("source") == "style_analogue"
        and r.get("best_analogue_score") is not None
        and float(r["best_analogue_score"]) < 0.55
    ]
    strong_analogue_styles.sort(key=lambda r: r["allocated_units"], reverse=True)
    weak_analogue_styles.sort(key=lambda r: r["allocated_units"], reverse=True)

    # avg units per (store × style) — measures spread thinness.
    distinct_styles = len(style_rows)
    if distinct_stores > 0 and distinct_styles > 0:
        avg_per_cell = allocated_units / (distinct_stores * distinct_styles)
    else:
        avg_per_cell = 0.0

    return _DecisionContext(
        session_id=session.id,
        brand_id=session.brand_id,
        verdict=str(decision.get("verdict") or "REVIEW_REQUIRED"),
        failure_class=str(decision.get("failure_class") or "STRATEGY"),
        health_score=int(session.health_score or 0),
        pct_store_history=pct_store_history,
        pct_style_analogue=pct_style_analogue,
        pct_category_bridge=pct_category_bridge,
        pct_grade=pct_grade,
        pct_minimum=pct_minimum,
        signal_grade=str(diag.get("signal_grade") or "LOW"),
        pct_confidence_high=high_conf / conf_total,
        pct_confidence_medium=med_conf / conf_total,
        pct_confidence_low=low_conf / conf_total,
        allocated_units=allocated_units,
        received_units=received_units,
        fill_ratio=fill_ratio,
        distinct_stores_with_alloc=distinct_stores,
        total_active_stores=total_active,
        avg_units_per_store_style=avg_per_cell,
        sub_scores={k: float(v) for k, v in sub_scores.items()},
        top_styles=top_styles,
        weak_analogue_styles=weak_analogue_styles[:5],
        strong_analogue_styles=strong_analogue_styles[:5],
        distinct_styles_allocated=distinct_styles,
    )


async def _aggregate_per_style(
    session_id: UUID, brand_id: UUID, db: AsyncSession
) -> list[dict[str, Any]]:
    """Group positive lines by ``style_code``, with rolled-up analogue
    scores and dominant ros_source. Bounded query — only positive lines."""
    rows = (
        await db.execute(
            select(
                SKU.style_code,
                AllocationLine.final_qty,
                AllocationLine.ai_confidence,
                AllocationLine.ai_reasoning,
            )
            .join(SKU, SKU.id == AllocationLine.sku_id)
            .where(
                AllocationLine.session_id == session_id,
                AllocationLine.brand_id == brand_id,
                AllocationLine.final_qty > 0,
            )
        )
    ).all()

    by_style: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "style_code": None,
            "allocated_units": 0,
            "lines": 0,
            "source_counts": defaultdict(int),
            "best_analogue_score": None,
            "analogue_scores": [],
            "high_conf_lines": 0,
        }
    )
    for row in rows:
        bucket = by_style[row.style_code]
        bucket["style_code"] = row.style_code
        bucket["allocated_units"] += int(row.final_qty or 0)
        bucket["lines"] += 1
        reasoning = row.ai_reasoning or {}
        source = reasoning.get("ros_source") or "unknown"
        bucket["source_counts"][source] += 1
        if (row.ai_confidence or "").upper() == "HIGH":
            bucket["high_conf_lines"] += 1
        analogue = reasoning.get("style_analogue_match") or {}
        score = analogue.get("best_score")
        if score is not None:
            try:
                score_f = float(score)
            except (TypeError, ValueError):
                score_f = None
            if score_f is not None:
                bucket["analogue_scores"].append(score_f)
                if (
                    bucket["best_analogue_score"] is None
                    or score_f > float(bucket["best_analogue_score"])
                ):
                    bucket["best_analogue_score"] = score_f

    flat: list[dict[str, Any]] = []
    for bucket in by_style.values():
        sources = bucket["source_counts"]
        dominant_source = max(sources.items(), key=lambda kv: kv[1])[0] if sources else "unknown"
        scores = bucket["analogue_scores"]
        flat.append(
            {
                "style_code": bucket["style_code"],
                "allocated_units": bucket["allocated_units"],
                "lines": bucket["lines"],
                "source": dominant_source,
                "best_analogue_score": (
                    round(bucket["best_analogue_score"], 4)
                    if bucket["best_analogue_score"] is not None
                    else None
                ),
                "avg_analogue_score": (
                    round(sum(scores) / len(scores), 4) if scores else None
                ),
                "high_conf_share": (
                    round(bucket["high_conf_lines"] / max(bucket["lines"], 1), 3)
                ),
            }
        )
    return flat


# ─── Rule pipeline ─────────────────────────────────────────────────────────


def _run_rule_pipeline(ctx: _DecisionContext) -> list[Action]:
    """Each rule may emit at most one Action. Order in the list does NOT
    determine priority — ranking is done by impact/confidence afterwards."""
    rules = (
        rule_buy_plan_undersized,
        rule_network_over_spread,
        rule_top_styles_scale_depth,
        rule_grade_reallocation,
        rule_analogue_dependence_alert,
        rule_data_quality_alert,
        rule_weak_analogue_caution,
        rule_healthy_release,
    )
    actions: list[Action] = []
    for rule in rules:
        out = rule(ctx)
        if out is not None:
            actions.append(out)
    return actions


def _rank_and_truncate(actions: list[Action], *, max_actions: int = 5) -> list[Action]:
    impact_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    conf_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    actions.sort(
        key=lambda a: (
            impact_rank.get(a.impact, 9),
            conf_rank.get(a.confidence, 9),
        )
    )
    return actions[:max_actions]


def _classify(ctx: _DecisionContext) -> str:
    """Three-class classification per the spec."""
    if ctx.signal_grade == "LOW" or ctx.pct_minimum >= 0.5 or ctx.failure_class == "DATA_QUALITY":
        return "DATA"
    if ctx.verdict in {"APPROVE", "APPROVE_WITH_CAUTION"} and ctx.signal_grade in {"HIGH", "MEDIUM"}:
        return "HEALTHY"
    return "STRATEGY"


def _build_summary(
    ctx: _DecisionContext, classification: str, actions: list[Action]
) -> str:
    """A 2-3 line paragraph that names the situation in business terms."""
    lead_action = actions[0].title if actions else None
    if classification == "HEALTHY":
        return (
            f"Plan is healthy. Engine ran with {ctx.signal_grade.lower()} signal across "
            f"{ctx.distinct_stores_with_alloc} of {ctx.total_active_stores} stores and "
            f"{ctx.distinct_styles_allocated} styles. "
            "Release as-is."
        )
    if classification == "DATA":
        return (
            "The plan can't be trusted yet — most lines fall back to minimum-presentation "
            "because the engine has no defensible demand signal. "
            "Fix the inputs before approving anything else: "
            + (lead_action or "re-upload sales with overlapping style codes or load an analogue map.")
        )
    # STRATEGY
    fill_pct = ctx.fill_ratio * 100
    return (
        f"Engine has real signal (signal grade: {ctx.signal_grade.lower()}, "
        f"{ctx.distinct_stores_with_alloc}/{ctx.total_active_stores} stores receiving) "
        f"but the buy plan or distribution shape is wrong — only {fill_pct:.0f}% "
        f"of received units could be responsibly distributed. "
        + (f"Lead action: {lead_action}." if lead_action else "Adjust the plan and re-run.")
    )


# ─── Rules ─────────────────────────────────────────────────────────────────


def rule_buy_plan_undersized(ctx: _DecisionContext) -> Action | None:
    """Engine wanted to ship more than the GRN had."""
    demand_align = float(ctx.sub_scores.get("demand_align", 50))
    if (
        ctx.signal_grade in {"HIGH", "MEDIUM"}
        and ctx.fill_ratio < 0.85
        and demand_align < 35
    ):
        # Suggest a +20% increase as a defensible starting point. The
        # planner adjusts; we just point the direction.
        suggested_pct = max(int(round((1.0 - ctx.fill_ratio) * 100 / 4) * 5), 15)
        return Action(
            id="INCREASE_TOTAL_BUY",
            category="Buy plan",
            title=f"Total buy is insufficient — increase top-volume styles by ~+{suggested_pct}%",
            description=(
                f"The engine wanted to allocate based on demand but only "
                f"{ctx.fill_ratio*100:.0f}% of received units cleared. The shortfall is "
                f"a buy quantity issue, not an engine call. Re-issue the buy with depth "
                f"weighted toward the top-{min(len(ctx.top_styles), 10)} styles where "
                f"demand signal is strongest."
            ),
            impact="HIGH",
            confidence="HIGH" if ctx.signal_grade == "HIGH" else "MEDIUM",
            data_backing=(
                f"Allocated {ctx.allocated_units:,} of {ctx.received_units:,} units · "
                f"demand_align {demand_align:.0f}/100 · signal {ctx.signal_grade.lower()}"
            ),
        )
    return None


def rule_network_over_spread(ctx: _DecisionContext) -> Action | None:
    """Inventory is spread too thin across too many stores."""
    if (
        ctx.distinct_stores_with_alloc >= 50
        and ctx.avg_units_per_store_style < 3.0
        and ctx.signal_grade in {"HIGH", "MEDIUM"}
    ):
        # Heuristic: cut to the stores that today get >= 1 unit per top-style.
        # Without that signal, suggest a 40% trim. Either way we give a target.
        suggested = max(int(ctx.distinct_stores_with_alloc * 0.6), 30)
        return Action(
            id="REDUCE_DISTRIBUTION",
            category="Distribution",
            title=(
                f"Reduce distribution from {ctx.distinct_stores_with_alloc} → ~{suggested} stores"
            ),
            description=(
                f"Per (store × style) depth is averaging "
                f"{ctx.avg_units_per_store_style:.1f} units — below the 3-unit "
                f"sellable-display threshold. Tighten the buy plan's store-group rule "
                f"so each store receives an assortment customers can actually shop."
            ),
            impact="HIGH",
            confidence="HIGH" if ctx.signal_grade == "HIGH" else "MEDIUM",
            data_backing=(
                f"avg {ctx.avg_units_per_store_style:.1f} units / (store × style) · "
                f"{ctx.distinct_stores_with_alloc} stores · {ctx.distinct_styles_allocated} styles"
            ),
        )
    return None


def rule_top_styles_scale_depth(ctx: _DecisionContext) -> Action | None:
    """Strong-analogue / store-history styles concentrated at the top —
    these are the ones to scale aggressively."""
    if not ctx.strong_analogue_styles and ctx.pct_store_history < 0.3:
        return None
    candidates = (
        ctx.strong_analogue_styles
        if ctx.strong_analogue_styles
        else [s for s in ctx.top_styles if s.get("source") in {"store_historical", "style_analogue"}]
    )
    if len(candidates) < 3:
        return None
    top_n = candidates[:10]
    style_codes = ", ".join(s["style_code"] for s in top_n[:3])
    more = f" (+{len(top_n) - 3} more)" if len(top_n) > 3 else ""
    return Action(
        id="SCALE_TOP_STYLES",
        category="Depth",
        title=f"Scale depth on the top {len(top_n)} styles by +25%",
        description=(
            f"These styles have strong analogue / direct-history signal "
            f"(best score ≥0.75) and currently anchor the allocation: "
            f"{style_codes}{more}. Increasing their depth by ~25% in the next "
            f"buy will lift overall sell-through more than spreading the increase "
            f"across the long tail."
        ),
        impact="HIGH" if len(top_n) >= 5 else "MEDIUM",
        confidence="HIGH",
        data_backing=(
            f"{len(ctx.strong_analogue_styles)} styles with analogue score ≥0.75 · "
            f"top {len(top_n)} = {sum(s['allocated_units'] for s in top_n):,} units"
        ),
    )


def rule_grade_reallocation(ctx: _DecisionContext) -> Action | None:
    """If a meaningful slice of stores receive nothing while signal is real,
    recommend a tilt toward higher-grade stores. The store-level shift is
    intentionally vague (we don't know the grade mix here) so the action
    points at the lever, not the exact percentage."""
    miss_share = (
        1 - ctx.distinct_stores_with_alloc / max(ctx.total_active_stores, 1)
    )
    if (
        ctx.signal_grade in {"HIGH", "MEDIUM"}
        and miss_share > 0.10
        and ctx.fill_ratio >= 0.40
    ):
        return Action(
            id="REALLOCATE_TO_TOP_GRADES",
            category="Reallocation",
            title="Tilt the next buy toward A+ / A grade stores",
            description=(
                f"{ctx.total_active_stores - ctx.distinct_stores_with_alloc} of "
                f"{ctx.total_active_stores} stores received zero units in this "
                f"allocation. Rather than forcing breadth, reinforce the cells "
                f"that already cleared — the top-grade stores have more reliable "
                f"sell-through and absorb the inventory faster."
            ),
            impact="MEDIUM",
            confidence="MEDIUM",
            data_backing=(
                f"{miss_share*100:.0f}% of active network received nothing · "
                f"signal grade {ctx.signal_grade.lower()}"
            ),
        )
    return None


def rule_analogue_dependence_alert(ctx: _DecisionContext) -> Action | None:
    """Flag heavy reliance on inferred (analogue + bridge) demand."""
    inferred_share = ctx.pct_style_analogue + ctx.pct_category_bridge
    if inferred_share >= 0.50 and ctx.pct_store_history < 0.20:
        return Action(
            id="ANALOGUE_DEPENDENCE",
            category="Risk",
            title=(
                f"{int(inferred_share*100)}% of lines rely on inferred demand "
                "— validate after Week 1 sell-through"
            ),
            description=(
                "The engine is leaning on style analogues and category bridge for "
                "most of this allocation because direct SKU history is thin. "
                "The math is defensible, but treat Week 1-2 sell-through as a "
                "live calibration: anything that under-performs the inferred "
                "ROS by >30% is a candidate for early markdown or transfer."
            ),
            impact="MEDIUM",
            confidence="HIGH",
            data_backing=(
                f"style_analogue {ctx.pct_style_analogue*100:.0f}% · "
                f"category_bridge {ctx.pct_category_bridge*100:.0f}% · "
                f"store_history {ctx.pct_store_history*100:.0f}%"
            ),
        )
    return None


def rule_data_quality_alert(ctx: _DecisionContext) -> Action | None:
    """Hard data-quality block — most lines fell to minimum-presentation."""
    if ctx.signal_grade == "LOW" or ctx.pct_minimum >= 0.5:
        return Action(
            id="FIX_DEMAND_INPUTS",
            category="Data",
            title="Fix demand inputs before approving anything else",
            description=(
                "The engine couldn't attach a defensible demand signal to most "
                "of the GRN. Don't release this allocation — it's effectively "
                "a guess. Either re-upload sales using the buy file's style "
                "codes (or analogue codes), or load a category × price-band "
                "analogue map so the bridge has more to work with. Re-run after."
            ),
            impact="HIGH",
            confidence="HIGH",
            data_backing=(
                f"signal grade {ctx.signal_grade.lower()} · "
                f"minimum_presentation {ctx.pct_minimum*100:.0f}% · "
                f"store_history {ctx.pct_store_history*100:.0f}%"
            ),
        )
    return None


def rule_weak_analogue_caution(ctx: _DecisionContext) -> Action | None:
    """Some analogue-driven styles have weak (<0.55) best scores."""
    if not ctx.weak_analogue_styles:
        return None
    weak_units = sum(int(s["allocated_units"]) for s in ctx.weak_analogue_styles)
    if weak_units < ctx.allocated_units * 0.05:
        return None  # ignore noise
    sample = ", ".join(s["style_code"] for s in ctx.weak_analogue_styles[:3])
    more = f" (+{len(ctx.weak_analogue_styles) - 3})" if len(ctx.weak_analogue_styles) > 3 else ""
    return Action(
        id="LIMIT_WEAK_ANALOGUE_DEPTH",
        category="Risk",
        title=(
            f"Treat {len(ctx.weak_analogue_styles)} weak-analogue styles as "
            "experimental — limit depth"
        ),
        description=(
            f"These styles matched analogues with similarity score <0.55, which "
            f"is below the trust line for full-depth distribution: {sample}{more}. "
            f"Halve their depth or restrict to A+ doors only until you have "
            f"actual sell-through to recalibrate."
        ),
        impact="MEDIUM",
        confidence="MEDIUM",
        data_backing=(
            f"{len(ctx.weak_analogue_styles)} styles with analogue score <0.55 · "
            f"{weak_units:,} units in plan"
        ),
    )


def rule_healthy_release(ctx: _DecisionContext) -> Action | None:
    """When everything is green, surface that as an explicit action."""
    if (
        ctx.verdict in {"APPROVE", "APPROVE_WITH_CAUTION"}
        and ctx.signal_grade in {"HIGH", "MEDIUM"}
        and ctx.fill_ratio >= 0.55
    ):
        return Action(
            id="RELEASE_PLAN",
            category="Healthy",
            title="Plan is releasable — approve and ship",
            description=(
                "Signal is strong, distribution is balanced, depth is sellable, "
                "and the engine's hard-constraint penalties did not fire. "
                "Approve the session as-is."
            ),
            impact="HIGH",
            confidence="HIGH",
            data_backing=(
                f"verdict {ctx.verdict} · health {ctx.health_score}/100 · "
                f"signal {ctx.signal_grade.lower()} · fill {ctx.fill_ratio*100:.0f}%"
            ),
        )
    return None
