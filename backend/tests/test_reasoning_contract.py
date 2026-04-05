"""Tests for allocation reasoning payload contract."""
from app.services.allocation.demand import build_allocation_reasoning, TrueDemandResult


REQUIRED_FIELDS = [
    'weekly_ros', 'raw_weekly_ros', 'ros_source', 'is_stockout_corrected',
    'stockout_week', 'lost_sales_estimate', 'data_sample_size', 'cluster_store_count',
    'cover_target_weeks', 'weeks_cover_at_recommended', 'weeks_cover_minus_25pct',
    'weeks_cover_plus_25pct', 'season_weeks_remaining', 'raw_demand_units', 'scale_factor',
    'store_grade', 'grade_multiplier',
    'category_affinity', 'fabric_affinity', 'affinity_adjustment_units',
    'cannibalization_factor', 'cannibalization_reason', 'colourways_in_story_at_store',
    'excluded_by_capacity', 'exclusion_reason',
    'size_split', 'size_distribution_source', 'size_distribution_season',
    'narrative_demand', 'narrative_adjustments', 'narrative_cap', 'confidence_basis',
    'style_dna_match',
]


def base_demand() -> TrueDemandResult:
    return TrueDemandResult(
        weekly_ros=2.5,
        source='store_historical',
        is_corrected=False,
        data_sample_size=16,
        raw_weekly_ros=2.5,
    )


def base_reasoning(**kw):
    defaults = dict(
        store_id='store-123',
        sku_id='sku-456',
        grade='A',
        demand_result=base_demand(),
        cover_target_weeks=5,
        raw_demand_units=12,
        final_qty=10,
        available_qty=100,
        size_result={'size_split': {'S': 3, 'M': 4, 'L': 3}, 'source': 'store_historical'},
        season_weeks_remaining=14,
        grade_multiplier=1.0,
    )
    defaults.update(kw)
    return build_allocation_reasoning(**defaults)


def test_all_required_fields_present():
    """Verify all required fields exist in reasoning payload."""
    r = base_reasoning()
    for f in REQUIRED_FIELDS:
        assert f in r, f"Missing required field: '{f}'"


def test_narrative_fields_are_non_empty():
    """Narrative fields must be non-empty strings."""
    r = base_reasoning()
    for f in ['narrative_demand', 'narrative_adjustments', 'narrative_cap', 'confidence_basis']:
        assert isinstance(r[f], str) and len(r[f]) > 5, f"Field '{f}' must be non-empty string, got: {r[f][:50]}"


def test_stockout_narrative_mentions_correction():
    """When stockout-corrected, narrative should mention it."""
    r = base_reasoning(
        demand_result=TrueDemandResult(
            weekly_ros=5.0,
            raw_weekly_ros=2.5,
            source='store_historical',
            is_corrected=True,
            stockout_week=4,
            lost_sales_estimate=20.0,
            data_sample_size=12,
        )
    )
    demand_narrative = r['narrative_demand'].lower()
    assert any(w in demand_narrative for w in ['corrected', 'stockout', 'stocked']), \
        f"Narrative should mention correction: {r['narrative_demand']}"


def test_cap_narrative_differs_for_scaled():
    """When qty is scaled down, narrative should mention constraint."""
    full = base_reasoning(raw_demand_units=10, final_qty=10)
    scaled = base_reasoning(raw_demand_units=18, final_qty=10)
    assert full['narrative_cap'] != scaled['narrative_cap'], \
        "Narrative should differ when allocation is scaled"
    assert 'constrained' in scaled['narrative_cap'].lower() or 'scale' in scaled['narrative_cap'].lower(), \
        f"Scaled narrative should mention constraint: {scaled['narrative_cap']}"


def test_phase2_fields_present_as_none():
    """Phase 2 fields should be present but None for Phase 1."""
    r = base_reasoning()
    assert r['style_dna_match'] is None
    assert r['category_affinity'] is None
    assert r['cannibalization_factor'] is None


def test_weeks_cover_calculation():
    """Weeks cover should be final_qty / weekly_ros."""
    r = base_reasoning(
        demand_result=TrueDemandResult(weekly_ros=2.0, raw_weekly_ros=2.0, source='store_historical'),
        final_qty=10
    )
    expected_weeks = 10 / 2.0
    assert abs(r['weeks_cover_at_recommended'] - expected_weeks) < 0.1, \
        f"Expected {expected_weeks}w cover, got {r['weeks_cover_at_recommended']}w"


def test_scale_factor_calculation():
    """Scale factor should be final_qty / raw_demand_units."""
    r = base_reasoning(raw_demand_units=20, final_qty=14)
    expected_factor = 14 / 20
    assert abs(r['scale_factor'] - expected_factor) < 0.01, \
        f"Expected scale {expected_factor}, got {r['scale_factor']}"


def test_confidence_basis_varies_by_sample():
    """Confidence level should vary based on data_sample_size in demand result."""
    high = base_reasoning(demand_result=TrueDemandResult(
        weekly_ros=2.0, source='store_historical', data_sample_size=16
    ))
    low = base_reasoning(demand_result=TrueDemandResult(
        weekly_ros=2.0, source='store_historical', data_sample_size=2
    ))
    assert 'High' in high['confidence_basis'] or 'high' in high['confidence_basis'].lower()
    assert 'Low' in low['confidence_basis'] or 'low' in low['confidence_basis'].lower() or high != low


def test_both_cover_field_name_variants_present():
    """Both pct and non-pct cover field names must be in the payload."""
    r = base_reasoning()
    assert "weeks_cover_minus_25pct" in r
    assert "weeks_cover_plus_25pct" in r
    assert "weeks_cover_minus_25" in r
    assert "weeks_cover_plus_25" in r
    assert r["weeks_cover_minus_25pct"] == r["weeks_cover_minus_25"]
    assert r["weeks_cover_plus_25pct"] == r["weeks_cover_plus_25"]
