from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

UNDER_COVERAGE_THRESHOLD = 0.80

DEFAULT_ACCEPTANCE_THRESHOLDS = {
    "override_rate_max": 0.20,
    "under_coverage_rate_max": 0.25,
    "grade_compliance_min": 0.98,
    "inventory_utilization_min": 0.95,
    "high_confidence_share_min": 0.50,
}

_GRADE_RANK = {"A+": 4, "A": 3, "B": 2, "C": 1}
_RISK_ORDER = {"PROVEN": 1, "CONFIDENT": 2, "EXPERIMENTAL": 3, "UNKNOWN": 99}


@dataclass(frozen=True)
class BenchmarkLine:
    final_qty: int
    ai_recommended_qty: int
    was_overridden: bool
    ai_confidence: str | None
    ros_source: str | None
    cover_target_weeks: float | None
    weeks_cover_at_recommended: float | None
    store_grade: str | None
    required_min_grade: str | None
    style_risk_group: str | None


def _normalize_grade(grade: str | None) -> str | None:
    cleaned = (grade or "").strip().upper()
    return cleaned if cleaned in _GRADE_RANK else None


def _grade_rank(grade: str | None) -> int:
    normalized = _normalize_grade(grade)
    if normalized is None:
        return 0
    return _GRADE_RANK[normalized]


def _normalize_risk_group(risk_group: str | None) -> str:
    cleaned = (risk_group or "").strip().upper()
    return cleaned if cleaned in {"PROVEN", "CONFIDENT", "EXPERIMENTAL"} else "UNKNOWN"


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _is_under_covered(weeks_cover: float | None, cover_target: float | None) -> bool:
    if weeks_cover is None or cover_target is None:
        return False
    if cover_target <= 0:
        return False
    return weeks_cover < (cover_target * UNDER_COVERAGE_THRESHOLD)


def _passes_grade_gate(store_grade: str | None, required_min_grade: str | None) -> bool:
    normalized_required = _normalize_grade(required_min_grade)
    if normalized_required is None:
        return True
    return _grade_rank(store_grade) >= _grade_rank(normalized_required)


def _new_bucket() -> dict[str, int]:
    return {
        "lines": 0,
        "allocated_units": 0,
        "overrides": 0,
        "under_covered": 0,
        "grade_violations": 0,
    }


def _bucket_to_payload(name: str, bucket: Mapping[str, int]) -> dict[str, int | float | str]:
    lines = int(bucket["lines"])
    return {
        "key": name,
        "lines": lines,
        "allocated_units": int(bucket["allocated_units"]),
        "override_rate": _rate(int(bucket["overrides"]), lines),
        "under_coverage_rate": _rate(int(bucket["under_covered"]), lines),
        "grade_compliance_rate": _rate(lines - int(bucket["grade_violations"]), lines),
    }


def _sorted_grade_keys(keys: Sequence[str]) -> list[str]:
    def order(key: str) -> tuple[int, str]:
        if key == "UNKNOWN":
            return (99, key)
        return (5 - _grade_rank(key), key)

    return sorted(keys, key=order)


def _sorted_risk_keys(keys: Sequence[str]) -> list[str]:
    return sorted(keys, key=lambda key: (_RISK_ORDER.get(key, 99), key))


def _resolve_utilization_threshold(
    base_threshold: float,
    season_context: Mapping[str, object] | None,
) -> tuple[float, str]:
    """Return (threshold, reason) based on season maturity."""
    if season_context is None:
        return base_threshold, "standard"

    is_cold_start = bool(season_context.get("is_cold_start", False))
    season_week = int(season_context.get("season_week", 99))

    if is_cold_start:
        return 0.55, "cold_start_season"
    if season_week <= 4:
        return 0.70, "early_season"
    return base_threshold, "standard"


def build_benchmark_report(
    lines: Sequence[BenchmarkLine],
    available_units_total: int,
    *,
    acceptance_thresholds: Mapping[str, float] | None = None,
    season_context: Mapping[str, object] | None = None,
) -> dict:
    thresholds = dict(DEFAULT_ACCEPTANCE_THRESHOLDS)
    if acceptance_thresholds:
        thresholds.update(acceptance_thresholds)

    utilization_threshold, utilization_reason = _resolve_utilization_threshold(
        base_threshold=float(thresholds["inventory_utilization_min"]),
        season_context=season_context,
    )

    if not lines:
        return {
            "summary": {
                "total_lines": 0,
                "allocated_units_total": 0,
                "available_units_total": int(max(0, available_units_total)),
                "override_rate": 0.0,
                "under_coverage_rate": 0.0,
                "grade_compliance_rate": 0.0,
                "inventory_utilization_rate": 0.0,
                "high_confidence_share": 0.0,
                "quality_score": 0.0,
            },
            "acceptance": {
                "overall_pass": False,
                "checks": [],
            },
            "demand_source_mix": [],
            "scorecards": {
                "by_grade": [],
                "by_style_risk_group": [],
            },
        }

    total_lines = len(lines)
    allocated_units_total = 0
    override_count = 0
    high_confidence_count = 0
    grade_compliant_count = 0
    under_covered_count = 0
    cover_eligible_count = 0

    source_counts: dict[str, int] = {}
    grade_buckets: dict[str, dict[str, int]] = {}
    risk_buckets: dict[str, dict[str, int]] = {}

    for line in lines:
        final_qty = max(int(line.final_qty or 0), 0)
        allocated_units_total += final_qty

        is_override = bool(line.was_overridden)
        if is_override:
            override_count += 1

        confidence = (line.ai_confidence or "").strip().upper()
        if confidence == "HIGH":
            high_confidence_count += 1

        source = (line.ros_source or "unknown").strip().lower() or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1

        is_under_covered = _is_under_covered(
            weeks_cover=line.weeks_cover_at_recommended,
            cover_target=line.cover_target_weeks,
        )
        if line.cover_target_weeks is not None and float(line.cover_target_weeks) > 0:
            cover_eligible_count += 1
        if is_under_covered:
            under_covered_count += 1

        grade_compliant = _passes_grade_gate(
            store_grade=line.store_grade,
            required_min_grade=line.required_min_grade,
        )
        if grade_compliant:
            grade_compliant_count += 1

        normalized_grade = _normalize_grade(line.store_grade) or "UNKNOWN"
        normalized_risk = _normalize_risk_group(line.style_risk_group)

        grade_bucket = grade_buckets.setdefault(normalized_grade, _new_bucket())
        risk_bucket = risk_buckets.setdefault(normalized_risk, _new_bucket())

        for bucket in (grade_bucket, risk_bucket):
            bucket["lines"] += 1
            bucket["allocated_units"] += final_qty
            bucket["overrides"] += int(is_override)
            bucket["under_covered"] += int(is_under_covered)
            bucket["grade_violations"] += int(not grade_compliant)

    override_rate = _rate(override_count, total_lines)
    under_coverage_denominator = cover_eligible_count if cover_eligible_count > 0 else total_lines
    under_coverage_rate = _rate(under_covered_count, under_coverage_denominator)
    grade_compliance_rate = _rate(grade_compliant_count, total_lines)
    high_confidence_share = _rate(high_confidence_count, total_lines)

    available = max(0, int(available_units_total))
    inventory_utilization_rate = _rate(allocated_units_total, available) if available > 0 else 0.0

    quality_score = round(
        100
        * (
            0.30 * max(0.0, 1.0 - override_rate)
            + 0.25 * grade_compliance_rate
            + 0.20 * min(inventory_utilization_rate, 1.0)
            + 0.15 * max(0.0, 1.0 - under_coverage_rate)
            + 0.10 * high_confidence_share
        ),
        1,
    )

    checks = [
        {
            "metric": "override_rate",
            "operator": "<=",
            "target": float(thresholds["override_rate_max"]),
            "actual": override_rate,
            "passed": override_rate <= float(thresholds["override_rate_max"]),
        },
        {
            "metric": "under_coverage_rate",
            "operator": "<=",
            "target": float(thresholds["under_coverage_rate_max"]),
            "actual": under_coverage_rate,
            "passed": under_coverage_rate <= float(thresholds["under_coverage_rate_max"]),
        },
        {
            "metric": "grade_compliance_rate",
            "operator": ">=",
            "target": float(thresholds["grade_compliance_min"]),
            "actual": grade_compliance_rate,
            "passed": grade_compliance_rate >= float(thresholds["grade_compliance_min"]),
        },
        {
            "metric": "inventory_utilization_rate",
            "operator": ">=",
            "target": utilization_threshold,
            "actual": inventory_utilization_rate,
            "passed": inventory_utilization_rate >= utilization_threshold,
        },
        {
            "metric": "high_confidence_share",
            "operator": ">=",
            "target": float(thresholds["high_confidence_share_min"]),
            "actual": high_confidence_share,
            "passed": high_confidence_share >= float(thresholds["high_confidence_share_min"]),
        },
    ]

    demand_source_mix = [
        {
            "source": source,
            "lines": count,
            "share": _rate(count, total_lines),
        }
        for source, count in sorted(source_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    by_grade = [
        _bucket_to_payload(key, grade_buckets[key]) for key in _sorted_grade_keys(list(grade_buckets.keys()))
    ]
    by_risk = [
        _bucket_to_payload(key, risk_buckets[key]) for key in _sorted_risk_keys(list(risk_buckets.keys()))
    ]

    return {
        "summary": {
            "total_lines": total_lines,
            "allocated_units_total": allocated_units_total,
            "available_units_total": available,
            "override_rate": override_rate,
            "under_coverage_rate": under_coverage_rate,
            "grade_compliance_rate": grade_compliance_rate,
            "inventory_utilization_rate": inventory_utilization_rate,
            "high_confidence_share": high_confidence_share,
            "quality_score": quality_score,
        },
        "acceptance": {
            "overall_pass": all(bool(check["passed"]) for check in checks),
            "checks": checks,
        },
        "utilization_threshold_applied": utilization_threshold,
        "utilization_threshold_reason": utilization_reason,
        "demand_source_mix": demand_source_mix,
        "scorecards": {
            "by_grade": by_grade,
            "by_style_risk_group": by_risk,
        },
    }
