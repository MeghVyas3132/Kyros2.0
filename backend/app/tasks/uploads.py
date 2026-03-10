import logging
import subprocess
import sys
from time import perf_counter

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.uploads.process_upload")
def process_upload_task(upload_id: str) -> dict:
    start = perf_counter()
    logger.info("upload_job_started", extra={"upload_id": upload_id})

    try:
        completed = subprocess.run(
            [sys.executable, "-m", "app.tasks.upload_runner", upload_id],
            check=True,
            capture_output=True,
            text=True,
        )
        result = {"upload_id": upload_id, "runner_output": completed.stdout.strip()}
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
