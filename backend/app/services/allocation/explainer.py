from __future__ import annotations

from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
	if value is None:
		return default
	if isinstance(value, (int, float)):
		return float(value)
	if isinstance(value, str):
		stripped = value.strip()
		if not stripped:
			return default
		token = stripped.split(" ", 1)[0].replace("%", "")
		try:
			return float(token)
		except ValueError:
			return default
	return default


def _to_int(value: Any, default: int = 0) -> int:
	return int(round(_to_float(value, float(default))))


def _to_bool(value: Any, default: bool = False) -> bool:
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		lowered = value.strip().lower()
		if lowered in {"true", "1", "yes", "y"}:
			return True
		if lowered in {"false", "0", "no", "n"}:
			return False
	return default


def normalize_reasoning(raw: dict[str, Any] | None) -> dict[str, Any]:
	payload = raw if isinstance(raw, dict) else {}

	weekly_ros = _to_float(payload.get("weekly_ros"), _to_float(payload.get("store_ros_attribute"), 0.0))
	cluster_ros = _to_float(payload.get("cluster_avg_ros_attribute"), weekly_ros)
	minus_cover = _to_float(payload.get("weeks_cover_minus_25"), _to_float(payload.get("weeks_cover_at_minus_25pct"), 0.0))
	plus_cover = _to_float(payload.get("weeks_cover_plus_25"), _to_float(payload.get("weeks_cover_at_plus_25pct"), 0.0))

	normalized = {
		"weekly_ros": weekly_ros,
		"store_ros_attribute": payload.get("store_ros_attribute")
		or f"{weekly_ros:.1f} units/week ({payload.get('ros_source', 'unknown')})",
		"cluster_avg_ros_attribute": payload.get("cluster_avg_ros_attribute")
		or f"{cluster_ros:.1f} units/week (cluster proxy)",
		"ros_vs_cluster_pct": _to_int(payload.get("ros_vs_cluster_pct"), 0),
		"ros_source": str(payload.get("ros_source") or payload.get("demand_source") or "minimum_presentation"),
		"is_stockout_corrected": _to_bool(payload.get("is_stockout_corrected"), False),
		"stockout_correction_applied": _to_bool(payload.get("stockout_correction_applied"), False),
		"stockout_week": payload.get("stockout_week"),
		"lost_sales_estimate": payload.get("lost_sales_estimate"),
		"cover_target_weeks": _to_int(payload.get("cover_target_weeks"), 0),
		"season_weeks_remaining": _to_int(payload.get("season_weeks_remaining"), 0),
		"raw_demand_units": _to_int(payload.get("raw_demand_units"), _to_int(payload.get("raw_demand"), 0)),
		"scale_factor": _to_float(payload.get("scale_factor"), 1.0),
		"store_grade": str(payload.get("store_grade") or "C"),
		"grade_multiplier": _to_float(payload.get("grade_multiplier"), 1.0),
		"weeks_cover_at_recommended": _to_float(payload.get("weeks_cover_at_recommended"), 0.0),
		"weeks_cover_minus_25": minus_cover,
		"weeks_cover_plus_25": plus_cover,
		"weeks_cover_at_minus_25pct": minus_cover,
		"weeks_cover_at_plus_25pct": plus_cover,
		"category_affinity": payload.get("category_affinity"),
		"fabric_affinity": payload.get("fabric_affinity"),
		"affinity_adjustment_units": payload.get("affinity_adjustment_units"),
		"cannibalization_factor": payload.get("cannibalization_factor"),
		"cannibalization_reason": payload.get("cannibalization_reason"),
		"colourways_in_story_at_store": payload.get("colourways_in_story_at_store"),
		"size_split": payload.get("size_split") if isinstance(payload.get("size_split"), dict) else {},
		"size_distribution_source": str(payload.get("size_distribution_source") or "brand_size_guide"),
		"size_distribution_season": payload.get("size_distribution_season"),
		"narrative_demand": str(payload.get("narrative_demand") or "Demand sourced from available history."),
		"narrative_adjustments": str(payload.get("narrative_adjustments") or "No adjustments applied."),
		"narrative_cap": str(payload.get("narrative_cap") or "No scaling required."),
		"confidence_basis": str(payload.get("confidence_basis") or "Based on available demand history."),
		"data_sample_size": _to_int(payload.get("data_sample_size"), 0),
		"style_dna_match": payload.get("style_dna_match"),
		"current_stock_cover_days": _to_float(payload.get("current_stock_cover_days"), 0.0),
		"display_capacity_available": payload.get("display_capacity_available"),
		"stockout_risk_at_lower_qty": _to_bool(payload.get("stockout_risk_at_lower_qty"), False),
		"climate_match": _to_bool(payload.get("climate_match"), True),
	}
	return normalized


def normalize_projections(raw: dict[str, Any] | None) -> dict[str, Any]:
	payload = raw if isinstance(raw, dict) else {}
	return {
		"size_split": payload.get("size_split") if isinstance(payload.get("size_split"), dict) else {},
		"size_distribution_source": str(payload.get("size_distribution_source") or "size_guide"),
		"cap_scale_factor": _to_float(payload.get("cap_scale_factor"), _to_float(payload.get("scale_factor"), 1.0)),
		"total_demand_before_cap": _to_int(
			payload.get("total_demand_before_cap"), _to_int(payload.get("raw_demand"), 0)
		),
		"available_qty": _to_int(payload.get("available_qty"), 0),
	}
