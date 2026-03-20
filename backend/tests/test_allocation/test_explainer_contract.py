from app.services.allocation.explainer import normalize_projections, normalize_reasoning


def test_normalize_reasoning_handles_legacy_payload() -> None:
    payload = {
        "store_grade": "A",
        "store_ros_attribute": 2.4,
        "cluster_avg_ros_attribute": 1.8,
        "ros_vs_cluster_pct": 33,
        "weeks_cover_at_minus_25pct": 2.1,
        "weeks_cover_at_plus_25pct": 3.6,
        "current_stock_cover_days": 14,
        "display_capacity_available": 10,
        "season_weeks_remaining": 9,
        "stockout_risk_at_lower_qty": True,
        "climate_match": True,
        "data_sample_size": 12,
        "confidence_basis": "legacy",
    }

    normalized = normalize_reasoning(payload)

    assert normalized["store_grade"] == "A"
    assert normalized["weekly_ros"] == 2.4
    assert normalized["weeks_cover_minus_25"] == 2.1
    assert normalized["weeks_cover_plus_25"] == 3.6
    assert normalized["weeks_cover_at_minus_25pct"] == 2.1
    assert normalized["weeks_cover_at_plus_25pct"] == 3.6
    assert normalized["confidence_basis"] == "legacy"


def test_normalize_reasoning_parses_string_ros() -> None:
    normalized = normalize_reasoning(
        {
            "store_ros_attribute": "2.7 units/week (grade_average)",
            "cluster_avg_ros_attribute": "2.0 units/week (cluster proxy)",
            "store_grade": "B",
        }
    )

    assert normalized["weekly_ros"] == 2.7
    assert normalized["store_grade"] == "B"
    assert normalized["ros_source"] == "minimum_presentation"


def test_normalize_projections_fills_defaults() -> None:
    normalized = normalize_projections({"scale_factor": 0.8})

    assert normalized["size_split"] == {}
    assert normalized["size_distribution_source"] == "size_guide"
    assert normalized["cap_scale_factor"] == 0.8
    assert normalized["total_demand_before_cap"] == 0
    assert normalized["available_qty"] == 0
