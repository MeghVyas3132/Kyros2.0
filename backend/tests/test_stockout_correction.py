"""Tests for stockout correction logic."""
from app.services.allocation.demand import _infer_stockout_week


def test_explicit_stockout_detection():
    """Test detection when sales go to zero mid-season."""
    sales_by_week = [10, 12, 9, 0, 0, 0, 0]
    week = _infer_stockout_week(sales_by_week)
    # Function returns idx-1 where idx is start of zeros, so for zeros at idx 3, returns 2
    assert week == 2, f"Expected stockout at week 2 (last selling week), got {week}"


def test_gradual_decline_not_stockout():
    """Test that gradual decline is not marked as stockout."""
    sales_by_week = [20, 18, 14, 10, 5, 2, 1]
    week = _infer_stockout_week(sales_by_week)
    assert week is None, "Gradual decline should not be marked as stockout"


def test_too_short_history_returns_none():
    """Test that insufficient history returns None."""
    sales_by_week = [5, 0, 0]
    week = _infer_stockout_week(sales_by_week)
    assert week is None, "Only 3 weeks - too short, should return None"


def test_single_week_zero_not_stockout():
    """Test that a single zero week is not detected as stockout."""
    sales_by_week = [10, 10, 0, 10, 10, 10, 10]
    week = _infer_stockout_week(sales_by_week)
    assert week is None, "Single zero week should not be marked as stockout"


def test_stockout_ros_calculation():
    """Test that corrected ROS exceeds raw ROS when stockout is detected."""
    sales_by_week = [10, 10, 10, 0, 0, 0]
    stockout_week = _infer_stockout_week(sales_by_week)
    assert stockout_week == 2, "Stockout should be detected at week 2 (last selling week)"
    
    # stockout_week (2) is the index of the last selling week
    selling_count = stockout_week + 1  # Count from 0, so 0, 1, 2 = 3 weeks
    selling_weeks = sales_by_week[:selling_count]
    corrected_ros = sum(selling_weeks) / selling_count
    raw_ros = sum(sales_by_week) / len(sales_by_week)
    
    assert corrected_ros > raw_ros, "Corrected ROS should exceed raw ROS"
    assert abs(corrected_ros - 10.0) < 0.01, f"Corrected ROS should be ~10.0, got {corrected_ros}"
    assert abs(raw_ros - 5.0) < 0.01, f"Raw ROS should be ~5.0, got {raw_ros}"


def test_lost_sales_estimate():
    """Test lost sales calculation."""
    sales_by_week = [10, 10, 10, 0, 0, 0]
    stockout_week = _infer_stockout_week(sales_by_week)
    # stockout_week is the last selling week index (2), so zero weeks start at 3
    zero_weeks_start = stockout_week + 1
    selling_weeks = sales_by_week[:zero_weeks_start]
    corrected_ros = sum(selling_weeks) / zero_weeks_start
    zero_weeks = len(sales_by_week) - zero_weeks_start
    lost_sales = corrected_ros * zero_weeks
    
    assert abs(lost_sales - 30.0) < 0.01, f"Lost sales should be ~30, got {lost_sales}"
