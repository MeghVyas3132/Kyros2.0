import asyncio
import json
import logging
import os
import sys
import traceback
from uuid import UUID

from app.database import AsyncSessionLocal
from app.models import Upload, UploadStatus
from app.services.ingestion.processor import process_upload
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)


async def _mark_upload_failed(
    upload_id: str,
    message: str,
    traceback_text: str,
    *,
    session_factory=None,
) -> None:
    """Best-effort: persist the failure on the Upload row so the UI doesn't
    show the row stuck on PROCESSING forever. Runs in a fresh session so a
    poisoned transaction from the failed run can't block this write.

    ``session_factory`` is injectable so tests can pass a function-scoped
    sessionmaker bound to the test's event loop. Production code calls
    without arguments and uses the module-level ``AsyncSessionLocal``.
    """
    factory = session_factory or AsyncSessionLocal
    try:
        async with factory() as db:
            upload = await db.get(Upload, UUID(upload_id))
            if upload is None:
                return
            # Build a *new* dict so SQLAlchemy's JSON mutation detection sees
            # the change. Mutating the loaded dict in place and reassigning
            # the same reference is a known no-op trap on JSON columns.
            existing = (
                dict(upload.error_summary)
                if isinstance(upload.error_summary, dict)
                else {}
            )
            existing["fatal_error"] = message
            existing["traceback"] = traceback_text[-4000:]
            upload.error_summary = existing
            upload.status = UploadStatus.FAILED
            upload.processing_completed_at = utcnow()
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to record upload error for %s", upload_id)


async def run_upload(upload_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        upload = await db.get(Upload, UUID(upload_id))
        if upload is None:
            raise ValueError(f"Upload {upload_id} not found")

        await process_upload(db, upload, task_id=os.getenv("UPLOAD_TASK_ID"))
        await db.commit()
        return {
            "upload_id": str(upload.id),
            "status": upload.status.value,
            "successful_rows": upload.successful_rows,
            "failed_rows": upload.failed_rows,
        }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.tasks.upload_runner <upload_id>")
    upload_id = sys.argv[1]
    try:
        result = asyncio.run(run_upload(upload_id))
        print(json.dumps(result))
    except BaseException as exc:  # noqa: BLE001
        # Persist the failure to the Upload row before the subprocess exits,
        # so the UI surfaces a real error message instead of "stuck processing".
        message = f"{exc.__class__.__name__}: {exc}"
        tb_text = traceback.format_exc()
        try:
            asyncio.run(_mark_upload_failed(upload_id, message, tb_text))
        except Exception:  # noqa: BLE001
            pass
        # Surface the original error so Celery's retry/backoff still kicks in.
        print(json.dumps({"error": message}), file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
