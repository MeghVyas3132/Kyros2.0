from app.services.allocation.demand import _infer_stockout_week


def test_infer_stockout_week_detects_zero_tail() -> None:
    series = [5, 4, 3, 2, 0, 0, 0, 0]
    assert _infer_stockout_week(series) == 3


def test_infer_stockout_week_returns_none_for_short_series() -> None:
    assert _infer_stockout_week([4, 3, 2, 1, 0]) is None


def test_infer_stockout_week_returns_none_when_no_stockout_pattern() -> None:
    series = [3, 2, 2, 1, 1, 2, 1, 1]
    assert _infer_stockout_week(series) is None
