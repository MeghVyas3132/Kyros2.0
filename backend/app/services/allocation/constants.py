from __future__ import annotations

GRADE_SCORES: dict[str, int] = {"A+": 5, "A": 4, "B": 3, "C": 2}
DEFAULT_GRADE: str = "C"
GRADE_MULTIPLIERS: dict[str, float] = {"A+": 1.25, "A": 1.00, "B": 0.75, "C": 0.50}

MINIMUM_ALLOCATION_QTY: int = 6
DEFAULT_MIN_PRESENTATION_QTY: int = 2
DEFAULT_SEASON_WEEKS_REMAINING: int = 8

DEFAULT_COVER_TARGETS: dict[tuple[str, str], int] = {
    ("PROVEN", "A+"): 7,
    ("PROVEN", "A"): 5,
    ("PROVEN", "B"): 4,
    ("PROVEN", "C"): 3,
    ("CONFIDENT", "A+"): 6,
    ("CONFIDENT", "A"): 5,
    ("CONFIDENT", "B"): 3,
    ("CONFIDENT", "C"): 2,
    ("EXPERIMENTAL", "A+"): 4,
    ("EXPERIMENTAL", "A"): 3,
    ("EXPERIMENTAL", "B"): 2,
    ("EXPERIMENTAL", "C"): 0,
}