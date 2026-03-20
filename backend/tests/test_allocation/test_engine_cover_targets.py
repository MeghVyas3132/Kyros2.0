from app.services.allocation.engine import AllocationEngine


def test_cover_target_lookup_for_known_tuple() -> None:
    engine = AllocationEngine()
    assert engine._cover_target_weeks("PROVEN", "A+") == 7
    assert engine._cover_target_weeks("EXPERIMENTAL", "C") == 0


def test_cover_target_falls_back_to_default_grade_mapping() -> None:
    engine = AllocationEngine()
    assert engine._cover_target_weeks("CONFIDENT", "UNKNOWN") == 2
    assert engine._cover_target_weeks("UNKNOWN", "A") == 5
