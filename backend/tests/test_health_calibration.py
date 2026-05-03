"""Health-scoring calibration + failure-class classification tests.

These tests pin the contract that determines what verdict a planner sees.
Pre-season planning has zero tolerance for false confidence, so each
canonical failure mode gets an explicit test:

  * DATA_QUALITY  — no SKU overlap, fallback dominant
  * ELIGIBILITY   — engine had signal but only one store qualified
  * STRATEGY      — bridge-dominant, real signal, but per-store depth too thin
  * NONE          — healthy, APPROVE-band

The hard-penalty caps are also pinned per signal grade so a future re-tune
can't silently regress cold-start brands back into REJECT.
"""
from __future__ import annotations

import pytest

from app.services.allocation.health import (
    AllocationHealthAnalyzer,
    _explain_block,
    compute_decision,
)


# ─── _explain_block: failure class taxonomy ─────────────────────────────────


def test_explain_block_returns_none_when_verdict_is_approve():
    reason, fix, klass = _explain_block(
        verdict="APPROVE",
        sub_scores={"coverage": 80, "demand_align": 80, "confidence": 80, "presentation": 80},
        line_diagnostics={"signal_grade": "HIGH"},
        context={},
    )
    assert reason is None
    assert fix is None
    assert klass == "NONE"


def test_explain_block_data_quality_when_no_signal_and_no_overlap():
    """SS26 buy file with zero-overlap SS25 sales. Engine had nothing to work
    with, so the block is upstream of the engine — DATA_QUALITY."""
    reason, fix, klass = _explain_block(
        verdict="REVIEW_REQUIRED",
        sub_scores={
            "coverage": 50, "demand_align": 0, "confidence": 20,
            "presentation": 100, "balance": 100,
        },
        line_diagnostics={
            "high_confidence_lines": 0,
            "moderate_confidence_lines": 0,
            "low_confidence_lines": 76658,
            "fallback_demand_ratio": 1.0,
            "signal_grade": "LOW",
            "sku_overlap_with_sales_pct": 0.003,
            "alloc_to_received_ratio": 0.0014,
            "distinct_stores_with_allocation": 1,
            "total_active_stores": 184,
        },
        context={},
    )
    assert klass == "DATA_QUALITY"
    assert "no overlap" in (reason or "").lower() or "no defensible demand" in (reason or "").lower()
    assert "analogue" in (fix or "").lower() or "style codes" in (fix or "").lower()


def test_explain_block_strategy_when_bridge_dominant_and_thin():
    """The cold-start unblock case: engine has real signal via the bridge,
    distributed across most stores, but per-store depth is shallow because
    the buy plan was sized for fewer stores than the network."""
    reason, fix, klass = _explain_block(
        verdict="REJECT",
        sub_scores={
            "coverage": 50, "demand_align": 60, "confidence": 70,
            "presentation": 30, "balance": 100,
        },
        line_diagnostics={
            "high_confidence_lines": 39000,
            "moderate_confidence_lines": 13000,
            "low_confidence_lines": 2000,
            "fallback_demand_ratio": 0.03,
            "medium_demand_ratio": 0.97,
            "strong_demand_ratio": 0.0,
            "signal_grade": "MEDIUM",
            "sku_overlap_with_sales_pct": 0.003,
            "alloc_to_received_ratio": 0.685,
            "distinct_stores_with_allocation": 179,
            "total_active_stores": 184,
        },
        context={},
    )
    assert klass == "STRATEGY"
    assert "thin" in (reason or "").lower() or "depth" in (reason or "").lower()
    assert "store" in (fix or "").lower() or "depth" in (fix or "").lower()


def test_explain_block_eligibility_when_few_stores_received():
    """Engine had signal but only one store qualified — store-group rule too
    tight. Distinct from STRATEGY because the fix is to loosen eligibility,
    not to change the buy plan."""
    reason, fix, klass = _explain_block(
        verdict="REVIEW_REQUIRED",
        sub_scores={
            "coverage": 50, "demand_align": 60, "confidence": 60,
            "presentation": 80, "balance": 100,
        },
        line_diagnostics={
            "high_confidence_lines": 50,
            "moderate_confidence_lines": 50,
            "low_confidence_lines": 5,
            "fallback_demand_ratio": 0.05,
            "medium_demand_ratio": 0.95,
            "signal_grade": "MEDIUM",
            "alloc_to_received_ratio": 0.30,
            "distinct_stores_with_allocation": 1,
            "total_active_stores": 184,
        },
        context={},
    )
    assert klass == "ELIGIBILITY"
    assert "store" in (reason or "").lower() and "1" in (reason or "")
    assert "store-group" in (fix or "").lower() or "eligibility" in (fix or "").lower() or "grade" in (fix or "").lower()


# ─── compute_decision: the verdict glue ─────────────────────────────────────


def test_compute_decision_threads_blocked_reason_and_failure_class():
    decision = compute_decision(
        health_score=58,
        risks=[],
        context={},
        sub_scores={
            "coverage": 60, "demand_align": 65, "confidence": 70,
            "presentation": 30, "balance": 100,
        },
        line_diagnostics={
            "high_confidence_lines": 100,
            "moderate_confidence_lines": 50,
            "low_confidence_lines": 5,
            "fallback_demand_ratio": 0.05,
            "medium_demand_ratio": 0.95,
            "strong_demand_ratio": 0.0,
            "signal_grade": "MEDIUM",
            "alloc_to_received_ratio": 0.65,
            "distinct_stores_with_allocation": 150,
            "total_active_stores": 180,
        },
    )
    # 58 → APPROVE_WITH_CAUTION → failure_class = NONE (we don't surface a
    # blocker for non-blocked verdicts).
    assert decision["verdict"] == "APPROVE_WITH_CAUTION"
    assert decision["failure_class"] == "NONE"
    assert decision["blocked_reason"] is None


def test_compute_decision_softens_reject_to_review_for_strategy_with_real_signal():
    """Per the user's calibration rule: signal-grade MEDIUM+ runs that fail
    on STRATEGY (buy plan / store-group footprint) should NOT shout REJECT.
    They should land in REVIEW_REQUIRED — actionable, not catastrophic —
    so the planner sees 'fix the buy plan' instead of 'do not release'."""
    decision = compute_decision(
        health_score=30,
        risks=[],
        context={},
        sub_scores={
            "coverage": 0, "demand_align": 0, "confidence": 86.9,
            "presentation": 98.3, "balance": 100,
        },
        line_diagnostics={
            "high_confidence_lines": 39353,
            "moderate_confidence_lines": 13624,
            "low_confidence_lines": 2248,
            "fallback_demand_ratio": 0.03,
            "medium_demand_ratio": 0.97,
            "strong_demand_ratio": 0.0,
            "signal_grade": "MEDIUM",
            "alloc_to_received_ratio": 0.413,
            "distinct_stores_with_allocation": 179,
            "total_active_stores": 184,
        },
    )
    assert decision["verdict"] == "REVIEW_REQUIRED"  # softened from REJECT
    assert decision["failure_class"] == "STRATEGY"
    assert "buy plan" in (decision["blocked_reason"] or "").lower() or "undersized" in (decision["blocked_reason"] or "").lower()


def test_compute_decision_keeps_reject_when_failure_is_data_quality():
    """The softening rule must NOT apply when the failure is DATA_QUALITY —
    a brand with no demand signal still has to see REJECT."""
    decision = compute_decision(
        health_score=22,
        risks=[],
        context={},
        sub_scores={
            "coverage": 50, "demand_align": 0, "confidence": 20,
            "presentation": 100, "balance": 100,
        },
        line_diagnostics={
            "high_confidence_lines": 0,
            "moderate_confidence_lines": 0,
            "low_confidence_lines": 76658,
            "fallback_demand_ratio": 1.0,
            "signal_grade": "LOW",
            "sku_overlap_with_sales_pct": 0.003,
            "alloc_to_received_ratio": 0.0014,
            "distinct_stores_with_allocation": 1,
            "total_active_stores": 184,
        },
    )
    assert decision["verdict"] == "REJECT"
    assert decision["failure_class"] == "DATA_QUALITY"


def test_compute_decision_carries_line_diagnostics_in_payload():
    """The frontend reads `line_diagnostics` directly off the decision blob.
    Make sure compute_decision passes it through unchanged."""
    diag = {
        "allocated_units": 87213,
        "received_units": 127251,
        "signal_grade": "MEDIUM",
        "distinct_stores_with_allocation": 179,
        "total_active_stores": 184,
        "sku_overlap_with_sales_pct": 0.003,
    }
    decision = compute_decision(
        health_score=22,
        risks=[],
        context={},
        sub_scores={"coverage": 50, "presentation": 30},
        line_diagnostics=diag,
    )
    for key in (
        "allocated_units",
        "received_units",
        "signal_grade",
        "distinct_stores_with_allocation",
    ):
        assert decision["line_diagnostics"][key] == diag[key]


# ─── Hard-penalty calibration per signal grade ──────────────────────────────


@pytest.mark.parametrize(
    "signal_grade,expected_max_penalty",
    [
        ("HIGH", 35),  # 20 stockout + 15 thin
        ("MEDIUM", 20),  # 12 stockout + 8 thin
        ("LOW", 10),  # 6 stockout + 4 thin
    ],
)
def test_hard_penalty_caps_per_signal_grade(signal_grade, expected_max_penalty):
    """A cold-start brand using the bridge (MEDIUM signal) MUST take a
    smaller hit than a brand with full store-historical signal (HIGH).
    Otherwise the health score lands in REJECT and the planner sees
    'do not release' for a perfectly defensible run."""
    analyzer = AllocationHealthAnalyzer.__new__(AllocationHealthAnalyzer)
    cov_m = {"pct_stockout": 1.0}  # max stockout
    pres_m = {"pct_thin": 1.0}     # max thin
    score, penalties = analyzer._apply_hard_penalties(
        100,  # base
        cov_m,
        pres_m,
        lines=[],
        signal_grade=signal_grade,
    )
    actual_penalty = 100 - score
    assert actual_penalty == expected_max_penalty, penalties
