from app.services.allocation.size_curve import reconcile_weighted_quantities


def test_reconcile_weighted_quantities_sums_to_target() -> None:
    weights = {"S": 1.0, "M": 2.0, "L": 1.0}
    result = reconcile_weighted_quantities(weights, total_units=14)
    assert sum(result.values()) == 14
    assert result["M"] >= result["S"]
    assert result["M"] >= result["L"]


def test_reconcile_weighted_quantities_empty_on_zero_units() -> None:
    assert reconcile_weighted_quantities({"S": 1}, total_units=0) == {}
