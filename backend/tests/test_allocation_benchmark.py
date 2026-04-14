from app.services.allocation.benchmark import BenchmarkLine, build_benchmark_report


def test_build_benchmark_report_computes_summary_and_acceptance() -> None:
    lines = [
        BenchmarkLine(
            final_qty=10,
            ai_recommended_qty=10,
            was_overridden=False,
            ai_confidence="HIGH",
            ros_source="store_historical",
            cover_target_weeks=5.0,
            weeks_cover_at_recommended=5.2,
            store_grade="A+",
            required_min_grade="A",
            style_risk_group="PROVEN",
        ),
        BenchmarkLine(
            final_qty=4,
            ai_recommended_qty=6,
            was_overridden=True,
            ai_confidence="LOW",
            ros_source="grade_average",
            cover_target_weeks=5.0,
            weeks_cover_at_recommended=2.2,
            store_grade="C",
            required_min_grade="B",
            style_risk_group="EXPERIMENTAL",
        ),
        BenchmarkLine(
            final_qty=0,
            ai_recommended_qty=3,
            was_overridden=True,
            ai_confidence="MEDIUM",
            ros_source="minimum_presentation",
            cover_target_weeks=None,
            weeks_cover_at_recommended=None,
            store_grade="A",
            required_min_grade=None,
            style_risk_group="CONFIDENT",
        ),
    ]

    report = build_benchmark_report(lines, available_units_total=20)
    summary = report["summary"]

    assert summary["total_lines"] == 3
    assert summary["allocated_units_total"] == 14
    assert summary["available_units_total"] == 20
    assert summary["override_rate"] == 0.6667
    assert summary["under_coverage_rate"] == 0.5
    assert summary["grade_compliance_rate"] == 0.6667
    assert summary["inventory_utilization_rate"] == 0.7
    assert summary["high_confidence_share"] == 0.3333

    assert report["acceptance"]["overall_pass"] is False
    check_by_metric = {item["metric"]: item for item in report["acceptance"]["checks"]}
    assert check_by_metric["override_rate"]["passed"] is False
    assert check_by_metric["grade_compliance_rate"]["passed"] is False


def test_build_benchmark_report_returns_grade_and_risk_scorecards() -> None:
    lines = [
        BenchmarkLine(
            final_qty=8,
            ai_recommended_qty=8,
            was_overridden=False,
            ai_confidence="HIGH",
            ros_source="store_historical",
            cover_target_weeks=4.0,
            weeks_cover_at_recommended=4.1,
            store_grade="A",
            required_min_grade="B",
            style_risk_group="PROVEN",
        ),
        BenchmarkLine(
            final_qty=5,
            ai_recommended_qty=7,
            was_overridden=True,
            ai_confidence="MEDIUM",
            ros_source="cluster_average",
            cover_target_weeks=4.0,
            weeks_cover_at_recommended=2.0,
            store_grade="A",
            required_min_grade="A",
            style_risk_group="PROVEN",
        ),
        BenchmarkLine(
            final_qty=3,
            ai_recommended_qty=3,
            was_overridden=False,
            ai_confidence="LOW",
            ros_source="grade_average",
            cover_target_weeks=3.0,
            weeks_cover_at_recommended=3.1,
            store_grade="B",
            required_min_grade="B",
            style_risk_group="CONFIDENT",
        ),
    ]

    report = build_benchmark_report(lines, available_units_total=18)

    by_grade = {item["key"]: item for item in report["scorecards"]["by_grade"]}
    by_risk = {item["key"]: item for item in report["scorecards"]["by_style_risk_group"]}

    assert by_grade["A"]["lines"] == 2
    assert by_grade["A"]["override_rate"] == 0.5
    assert by_grade["B"]["lines"] == 1
    assert by_grade["B"]["grade_compliance_rate"] == 1.0

    assert by_risk["PROVEN"]["lines"] == 2
    assert by_risk["PROVEN"]["under_coverage_rate"] == 0.5
    assert by_risk["CONFIDENT"]["lines"] == 1
