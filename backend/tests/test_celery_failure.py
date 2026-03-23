"""Tests for Celery task failure handling and session status updates."""
from app.models.allocation import AllocationStatus


def test_failed_allocation_status_constant_exists():
    """
    Verify that AllocationStatus.FAILED exists and can be used.
    """
    assert hasattr(AllocationStatus, 'FAILED')
    # Verify it's a valid enum value
    assert AllocationStatus.FAILED.value == 'FAILED'


def test_under_review_guard_constant_exists():
    """
    Verify that AllocationStatus.UNDER_REVIEW exists.
    """
    assert hasattr(AllocationStatus, 'UNDER_REVIEW')
    assert AllocationStatus.UNDER_REVIEW.value == 'UNDER_REVIEW'
