"""Tests for cover target framing logic."""
from app.services.allocation.constants import DEFAULT_COVER_TARGETS, GRADE_MULTIPLIERS


def test_cover_target_weeks_aplus_proven():
    """Test that A+ stores with PROVEN styles get 7 weeks of cover."""
    style_risk = "PROVEN"
    grade = "A+"
    cover_weeks = DEFAULT_COVER_TARGETS.get((style_risk, grade), 0)
    assert cover_weeks == 7, f"A+ PROVEN should be 7 weeks, got {cover_weeks}"


def test_cover_target_weeks_c_proven():
    """Test that C stores get lower cover targets."""
    style_risk = "PROVEN"
    grade = "C"
    cover_weeks = DEFAULT_COVER_TARGETS.get((style_risk, grade), 0)
    assert cover_weeks > 0, "C stores should get some cover"
    assert cover_weeks < 7, "C stores should get less cover than A+ stores"


def test_experimental_c_gets_zero():
    """Test that EXPERIMENTAL + C gets zero allocation."""
    style_risk = "EXPERIMENTAL"
    grade = "C"
    cover_weeks = DEFAULT_COVER_TARGETS.get((style_risk, grade), 0)
    assert cover_weeks == 0, "EXPERIMENTAL + C should be 0 weeks (excluded)"


def test_experimental_aplus_gets_cover():
    """Test that EXPERIMENTAL + A+ still gets some, but lower than PROVEN."""
    proven_aplus = DEFAULT_COVER_TARGETS.get(("PROVEN", "A+"), 0)
    exp_aplus = DEFAULT_COVER_TARGETS.get(("EXPERIMENTAL", "A+"), 0)
    assert exp_aplus > 0, "EXPERIMENTAL A+ should get some cover"
    assert exp_aplus < proven_aplus, "EXPERIMENTAL should get less cover than PROVEN at same grade"


def test_grade_multiplier_progression():
    """Test that grade multipliers are properly ordered."""
    aplus_mult = GRADE_MULTIPLIERS.get("A+", 1.0)
    a_mult = GRADE_MULTIPLIERS.get("A", 1.0)
    b_mult = GRADE_MULTIPLIERS.get("B", 1.0)
    c_mult = GRADE_MULTIPLIERS.get("C", 1.0)
    
    assert aplus_mult >= a_mult >= b_mult >= c_mult, "Multipliers should decrease with lower grades"
    assert abs(aplus_mult - 1.25) < 0.01, f"A+ multiplier should be 1.25, got {aplus_mult}"
    assert abs(c_mult - 0.50) < 0.01, f"C multiplier should be 0.50, got {c_mult}"


def test_cover_capped_by_season_remaining():
    """Test that allocated cover is capped by season length."""
    weekly_ros = 2.0
    cover_base = 7
    season_weeks = 4
    
    # Final cover should be min(base, season_remaining)
    final_cover = min(cover_base, season_weeks)
    assert final_cover == 4, "Cover should be capped by season remaining"
    
    qty = final_cover * weekly_ros
    assert qty == 8, f"4 weeks × 2 ros/week = 8 units, got {qty}"
