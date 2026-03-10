from uuid import uuid4

from app.services.allocation.engine import AllocationEngine, ScoreData


def test_distribute_concentrated_respects_max_stores_and_totals() -> None:
    engine = AllocationEngine()
    eligible = {
        uuid4(): ScoreData(score=10, store_ros=2.0, grade_score=5, current_cover=3.0, sample_size=20, store_grade="A+"),
        uuid4(): ScoreData(score=9, store_ros=1.8, grade_score=4, current_cover=4.0, sample_size=20, store_grade="A"),
        uuid4(): ScoreData(score=8, store_ros=1.7, grade_score=4, current_cover=5.0, sample_size=20, store_grade="A"),
        uuid4(): ScoreData(score=7, store_ros=1.6, grade_score=3, current_cover=6.0, sample_size=20, store_grade="B"),
    }
    allocation = engine._distribute_concentrated(
        eligible_stores=eligible,
        available_units=24,
        max_stores=3,
        min_units_per_store=6,
    )
    assert len(allocation) == 3
    assert sum(allocation.values()) == 24
    assert all(qty >= 6 for qty in allocation.values())


def test_distribute_concentrated_falls_back_to_single_store_when_too_few_units() -> None:
    engine = AllocationEngine()
    eligible = {
        uuid4(): ScoreData(score=10, store_ros=2.0, grade_score=5, current_cover=3.0, sample_size=20, store_grade="A+"),
        uuid4(): ScoreData(score=9, store_ros=1.8, grade_score=4, current_cover=4.0, sample_size=20, store_grade="A"),
    }
    allocation = engine._distribute_concentrated(
        eligible_stores=eligible,
        available_units=4,
        max_stores=5,
        min_units_per_store=6,
    )
    assert len(allocation) == 1
    assert sum(allocation.values()) == 4
