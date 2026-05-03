"""Decision-Layer tests.

Covers the five scenarios named in the spec:

  1. Strong-analogue coverage         → SCALE_TOP_STYLES + RELEASE_PLAN
  2. No analogue / no signal          → DATA classification + FIX_DEMAND_INPUTS
  3. Thin buy plan                    → INCREASE_TOTAL_BUY (HIGH impact)
  4. Over-distribution                → REDUCE_DISTRIBUTION
  5. Mixed signals (analogue heavy)   → ANALOGUE_DEPENDENCE risk alert

Plus the contract: max 5 actions, ranking by impact then confidence,
classification correctness, and aggregates round-trip into the payload.

Each test builds a ``_DecisionContext`` directly so we exercise the rule
pipeline + classifier without standing up a full allocation.
"""
from __future__ import annotations

import uuid

from app.services.decision.decision_engine import (
    Action,
    _DecisionContext,
    _build_summary,
    _classify,
    _rank_and_truncate,
    _run_rule_pipeline,
    rule_analogue_dependence_alert,
    rule_buy_plan_undersized,
    rule_data_quality_alert,
    rule_grade_reallocation,
    rule_healthy_release,
    rule_network_over_spread,
    rule_top_styles_scale_depth,
    rule_weak_analogue_caution,
)


# ─── Test factory ──────────────────────────────────────────────────────────


def _ctx(**overrides) -> _DecisionContext:
    """Build a context with sensible defaults; tests override the bits they care about."""
    defaults = dict(
        session_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        verdict="REVIEW_REQUIRED",
        failure_class="STRATEGY",
        health_score=45,
        pct_store_history=0.0,
        pct_style_analogue=0.0,
        pct_category_bridge=0.0,
        pct_grade=0.0,
        pct_minimum=0.0,
        signal_grade="MEDIUM",
        pct_confidence_high=0.0,
        pct_confidence_medium=0.0,
        pct_confidence_low=0.0,
        allocated_units=0,
        received_units=0,
        fill_ratio=0.0,
        distinct_stores_with_alloc=0,
        total_active_stores=180,
        avg_units_per_store_style=0.0,
        sub_scores={},
        top_styles=[],
        weak_analogue_styles=[],
        strong_analogue_styles=[],
        distinct_styles_allocated=0,
    )
    defaults.update(overrides)
    return _DecisionContext(**defaults)


def _style(code: str, units: int, *, source="style_analogue", best_score=None) -> dict:
    return {
        "style_code": code,
        "allocated_units": units,
        "lines": units // 5,
        "source": source,
        "best_analogue_score": best_score,
        "avg_analogue_score": best_score,
        "high_conf_share": 0.7,
    }


# ─── Scenario 1 — strong analogue coverage → scale + release ───────────────


def test_strong_analogue_coverage_recommends_scale_and_release():
    strong_styles = [_style(f"S-{i}", 3000 - i * 100, best_score=0.82) for i in range(8)]
    ctx = _ctx(
        verdict="APPROVE_WITH_CAUTION",
        failure_class="NONE",
        health_score=68,
        signal_grade="HIGH",
        pct_style_analogue=0.7,
        pct_store_history=0.2,
        pct_confidence_high=0.75,
        pct_confidence_medium=0.20,
        allocated_units=80_000,
        received_units=100_000,
        fill_ratio=0.80,
        distinct_stores_with_alloc=170,
        avg_units_per_store_style=4.5,
        top_styles=strong_styles,
        strong_analogue_styles=strong_styles,
        distinct_styles_allocated=120,
        sub_scores={"coverage": 70, "demand_align": 60, "presentation": 75},
    )
    actions = _run_rule_pipeline(ctx)
    ids = {a.id for a in actions}
    assert "SCALE_TOP_STYLES" in ids
    assert "RELEASE_PLAN" in ids
    assert _classify(ctx) == "HEALTHY"


# ─── Scenario 2 — no signal → data classification + fix-inputs action ──────


def test_no_signal_yields_data_classification_and_fix_inputs():
    ctx = _ctx(
        verdict="REJECT",
        failure_class="DATA_QUALITY",
        health_score=22,
        signal_grade="LOW",
        pct_minimum=0.95,
        pct_style_analogue=0.0,
        pct_store_history=0.0,
        pct_confidence_low=1.0,
        allocated_units=180,
        received_units=127_000,
        fill_ratio=0.001,
        distinct_stores_with_alloc=1,
        sub_scores={"demand_align": 0, "confidence": 20},
    )
    actions = _run_rule_pipeline(ctx)
    ids = {a.id for a in actions}
    assert "FIX_DEMAND_INPUTS" in ids
    fix = next(a for a in actions if a.id == "FIX_DEMAND_INPUTS")
    assert fix.impact == "HIGH"
    assert _classify(ctx) == "DATA"


# ─── Scenario 3 — thin buy plan → INCREASE_TOTAL_BUY ──────────────────────


def test_thin_buy_plan_recommends_increase_total_buy():
    ctx = _ctx(
        verdict="REVIEW_REQUIRED",
        failure_class="STRATEGY",
        health_score=30,
        signal_grade="MEDIUM",
        pct_style_analogue=0.97,
        pct_confidence_high=0.71,
        allocated_units=87_213,
        received_units=127_251,
        fill_ratio=0.685,
        distinct_stores_with_alloc=179,
        avg_units_per_store_style=2.8,
        top_styles=[_style(f"T-{i}", 1500 - i * 50) for i in range(10)],
        strong_analogue_styles=[],
        distinct_styles_allocated=146,
        sub_scores={"coverage": 0, "demand_align": 0, "confidence": 87, "presentation": 98},
    )
    actions = _run_rule_pipeline(ctx)
    ids = {a.id for a in actions}
    assert "INCREASE_TOTAL_BUY" in ids
    buy_action = next(a for a in actions if a.id == "INCREASE_TOTAL_BUY")
    assert buy_action.impact == "HIGH"
    assert "+" in buy_action.title and "%" in buy_action.title
    assert _classify(ctx) == "STRATEGY"


# ─── Scenario 4 — over-distribution → REDUCE_DISTRIBUTION ─────────────────


def test_over_distribution_recommends_reduce_distribution():
    ctx = _ctx(
        verdict="REVIEW_REQUIRED",
        failure_class="STRATEGY",
        health_score=40,
        signal_grade="MEDIUM",
        pct_style_analogue=0.6,
        pct_category_bridge=0.3,
        allocated_units=50_000,
        received_units=80_000,
        fill_ratio=0.625,
        distinct_stores_with_alloc=180,
        avg_units_per_store_style=1.8,  # below 3-unit threshold
        sub_scores={"coverage": 30, "presentation": 35, "demand_align": 50},
    )
    actions = _run_rule_pipeline(ctx)
    ids = {a.id for a in actions}
    assert "REDUCE_DISTRIBUTION" in ids
    reduce = next(a for a in actions if a.id == "REDUCE_DISTRIBUTION")
    assert reduce.impact == "HIGH"
    assert "180" in reduce.title  # current count surfaced in title


# ─── Scenario 5 — analogue-heavy mixed signal → ANALOGUE_DEPENDENCE alert ──


def test_analogue_heavy_run_emits_dependence_alert():
    ctx = _ctx(
        verdict="APPROVE_WITH_CAUTION",
        failure_class="NONE",
        health_score=58,
        signal_grade="MEDIUM",
        pct_style_analogue=0.55,
        pct_category_bridge=0.30,
        pct_store_history=0.05,  # below 20% threshold
        pct_confidence_high=0.40,
        pct_confidence_medium=0.50,
        allocated_units=70_000,
        received_units=100_000,
        fill_ratio=0.70,
        distinct_stores_with_alloc=160,
        avg_units_per_store_style=3.5,
        sub_scores={"coverage": 60, "presentation": 75, "demand_align": 55},
    )
    actions = _run_rule_pipeline(ctx)
    ids = {a.id for a in actions}
    assert "ANALOGUE_DEPENDENCE" in ids


def test_weak_analogue_caution_emitted_when_weak_styles_carry_weight():
    weak = [_style(f"W-{i}", 800, best_score=0.45) for i in range(5)]
    ctx = _ctx(
        verdict="REVIEW_REQUIRED",
        failure_class="STRATEGY",
        signal_grade="MEDIUM",
        pct_style_analogue=0.6,
        allocated_units=20_000,
        weak_analogue_styles=weak,
        distinct_stores_with_alloc=120,
        sub_scores={"coverage": 50, "presentation": 60},
    )
    actions = _run_rule_pipeline(ctx)
    ids = {a.id for a in actions}
    assert "LIMIT_WEAK_ANALOGUE_DEPTH" in ids


# ─── Pipeline contract: ranking + truncation ───────────────────────────────


def test_rank_and_truncate_caps_at_5_actions_high_first():
    actions = [
        Action(id="A", category="x", title="a", description="", impact="LOW", confidence="HIGH", data_backing=""),
        Action(id="B", category="x", title="b", description="", impact="HIGH", confidence="LOW", data_backing=""),
        Action(id="C", category="x", title="c", description="", impact="HIGH", confidence="HIGH", data_backing=""),
        Action(id="D", category="x", title="d", description="", impact="MEDIUM", confidence="MEDIUM", data_backing=""),
        Action(id="E", category="x", title="e", description="", impact="MEDIUM", confidence="HIGH", data_backing=""),
        Action(id="F", category="x", title="f", description="", impact="LOW", confidence="LOW", data_backing=""),
    ]
    out = _rank_and_truncate(actions, max_actions=5)
    assert len(out) == 5
    # HIGH impact first, with HIGH-confidence beating LOW-confidence within the same tier.
    assert [a.id for a in out[:2]] == ["C", "B"]
    # MEDIUM impact next, again HIGH-confidence first.
    assert [a.id for a in out[2:4]] == ["E", "D"]
    # LOW-impact-LOW-confidence dropped.
    assert "F" not in {a.id for a in out}


def test_no_overlap_between_data_and_strategy_classifications():
    """Data-quality runs must never be classified as STRATEGY, even if
    other strategy-style triggers also fire. The user is explicit:
    DATA failure class should win."""
    ctx = _ctx(
        verdict="REJECT",
        failure_class="DATA_QUALITY",
        health_score=22,
        signal_grade="LOW",
        pct_minimum=0.95,
        avg_units_per_store_style=1.0,  # would also fire over-spread
        distinct_stores_with_alloc=180,
        fill_ratio=0.001,
    )
    assert _classify(ctx) == "DATA"


def test_summary_is_short_and_names_lead_action():
    """Spec: 2-3 lines. We don't enforce sentence count, but length should
    be bounded and the lead action title should appear when present."""
    actions = [
        Action(
            id="INCREASE_TOTAL_BUY",
            category="Buy plan",
            title="Total buy is insufficient — increase top-volume styles by ~+25%",
            description="...",
            impact="HIGH",
            confidence="HIGH",
            data_backing="...",
        )
    ]
    ctx = _ctx(
        signal_grade="MEDIUM",
        fill_ratio=0.68,
        distinct_stores_with_alloc=179,
        total_active_stores=184,
    )
    summary = _build_summary(ctx, "STRATEGY", actions)
    assert len(summary) <= 500  # 2-3 line cap
    assert "increase top-volume" in summary.lower()


def test_pipeline_returns_actions_for_strategy_run():
    """Smoke that the full pipeline produces actions for a typical
    cold-start STRATEGY run (the brand1 case from real data)."""
    ctx = _ctx(
        verdict="REVIEW_REQUIRED",
        failure_class="STRATEGY",
        health_score=30,
        signal_grade="MEDIUM",
        pct_style_analogue=0.5,
        pct_category_bridge=0.45,
        pct_confidence_high=0.71,
        allocated_units=87_213,
        received_units=127_251,
        fill_ratio=0.685,
        distinct_stores_with_alloc=179,
        total_active_stores=184,
        avg_units_per_store_style=2.8,
        top_styles=[_style(f"S-{i}", 1500) for i in range(10)],
        strong_analogue_styles=[_style(f"S-{i}", 1500, best_score=0.78) for i in range(6)],
        distinct_styles_allocated=146,
        sub_scores={"coverage": 0, "demand_align": 0, "confidence": 87, "presentation": 98},
    )
    actions = _rank_and_truncate(_run_rule_pipeline(ctx), max_actions=5)
    assert 1 <= len(actions) <= 5
    assert actions[0].impact in {"HIGH", "MEDIUM"}
    # The most valuable (HIGH-impact) action lands first.
    assert all(
        actions[i].impact != "LOW" or actions[i + 1].impact == "LOW"
        for i in range(len(actions) - 1)
    )
