import logging
import subprocess
import sys
from time import perf_counter

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_upload_subprocess(upload_id: str) -> dict:
    completed = subprocess.run(
        [sys.executable, "-m", "app.tasks.upload_runner", upload_id],
        check=True,
        capture_output=True,
        text=True,
    )
    return {"upload_id": upload_id, "runner_output": completed.stdout.strip()}


def process_upload_sync(upload_id: str, brand_id: str | None = None) -> dict:
    del brand_id
    return _run_upload_subprocess(upload_id)


async def process_upload_with_fallback(upload_id: str, brand_id: str) -> dict:
    try:
        if not celery_app.control.ping(timeout=1.0):
            raise RuntimeError("Celery worker not reachable")
        task = process_upload_task.apply_async(args=[upload_id, brand_id], timeout=2)
        return {"mode": "async", "task_id": task.id}
    except Exception:
        logger.warning("Celery unavailable, processing upload %s synchronously", upload_id)
        process_upload_sync(upload_id, brand_id)
        return {"mode": "sync", "task_id": None}


@celery_app.task(name="app.tasks.uploads.process_upload")
def process_upload_task(upload_id: str, brand_id: str | None = None) -> dict:
    start = perf_counter()
    logger.info("upload_job_started", extra={"upload_id": upload_id})

    try:
        result = _run_upload_subprocess(upload_id)
        logger.info(
            "upload_job_completed",
            extra={"duration_seconds": round(perf_counter() - start, 3), **result},
        )
        return result
    except Exception:
        logger.exception(
            "upload_job_failed",
            extra={"duration_seconds": round(perf_counter() - start, 3), "upload_id": upload_id},
        )
        raise
