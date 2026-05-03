"""Regression test: the upload runner must persist FAILED status when the
ingestion pipeline raises, so the UI shows a real error instead of "Processing"
forever.

Background: a real bring-up bug had a SUPER_ADMIN attempt to ingest a buy
file into the sentinel brand (no season) — the processor raised, the
subprocess exited 1, and the Upload row stayed PROCESSING forever. This
test pins the contract that ``run_upload`` + the ``main()`` wrapper write
``status=FAILED`` and capture the error message in ``error_summary``.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Upload, UploadStatus, UploadType
from app.tasks.upload_runner import _mark_upload_failed


pytestmark = pytest.mark.asyncio


async def test_run_upload_marks_row_failed_on_exception(db, engine, tenant):
    """When ``run_upload`` raises (here: missing s3_key file), the uploads row
    should end up in FAILED status with the error captured. We exercise this
    by calling ``_mark_upload_failed`` directly — the same helper that
    ``main()`` uses on top-level exceptions."""
    upload = Upload(
        brand_id=tenant.brand_id,
        uploaded_by=tenant.user_id,
        upload_type=UploadType.BUY_FILE,
        filename="missing.csv",
        s3_key="local/does-not-exist.csv",
        status=UploadStatus.PROCESSING,
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)

    # Simulate a runner crash → record it. We bind the helper's session to
    # the test's function-scoped engine so it shares this test's event loop.
    test_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _mark_upload_failed(
        str(upload.id),
        "ValueError: No season found for this brand.",
        "Traceback (most recent call last):\n  ...\nValueError: No season found",
        session_factory=test_factory,
    )

    # _mark_upload_failed wrote via its own session; we need to evict the
    # cached row so SQLAlchemy re-reads from DB.
    await db.refresh(upload)
    refreshed = upload
    assert refreshed is not None
    assert refreshed.status == UploadStatus.FAILED
    assert refreshed.processing_completed_at is not None
    assert isinstance(refreshed.error_summary, dict)
    assert "fatal_error" in refreshed.error_summary
    assert "No season" in refreshed.error_summary["fatal_error"]
    assert refreshed.error_summary["traceback"].startswith("Traceback")


async def test_run_upload_failed_marker_is_idempotent(db, engine, tenant):
    """Calling ``_mark_upload_failed`` twice should not raise — the helper is
    used from a poisoned txn context, and we never want it to make the
    failure worse."""
    upload = Upload(
        brand_id=tenant.brand_id,
        uploaded_by=tenant.user_id,
        upload_type=UploadType.SALES,
        filename="missing.csv",
        s3_key="local/does-not-exist.csv",
        status=UploadStatus.PROCESSING,
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)

    test_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _mark_upload_failed(str(upload.id), "first error", "tb1", session_factory=test_factory)
    await _mark_upload_failed(str(upload.id), "second error", "tb2", session_factory=test_factory)

    await db.refresh(upload)
    refreshed = upload
    assert refreshed.status == UploadStatus.FAILED
    # Last writer wins on the message — that's fine for this contract.
    assert refreshed.error_summary["fatal_error"] == "second error"


async def test_run_upload_no_op_when_id_missing():
    """Helper must not raise when handed a non-existent upload id (e.g. row
    deleted between subprocess start and crash)."""
    fake = str(uuid.uuid4())
    # Should swallow the absence and return None.
    await _mark_upload_failed(fake, "any", "any")
