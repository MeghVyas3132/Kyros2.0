"""
Celery task that runs the allocation engine in the background.
The HTTP endpoint creates a GENERATING session and dispatches this task.
"""
import asyncio
import logging
from time import perf_counter

from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run_allocation(session_id: str, grn_id: str, brand_id: str) -> dict:
    from uuid import UUID
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import AllocationSession, AllocationStatus
    from app.services.allocation.engine import AllocationEngine

    engine = AllocationEngine()

    async with AsyncSessionLocal() as db:
        session = await engine.generate(UUID(grn_id), UUID(brand_id), db)
        await db.commit()
        return {
            "session_id": str(session.id),
            "status": session.status.value if hasattr(session.status, "value") else str(session.status),
            "total_units": session.total_units_recommended,
        }


async def _mark_failed(session_id: str, reason: str) -> None:
    from uuid import UUID
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import AllocationSession, AllocationStatus

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(AllocationSession).where(AllocationSession.id == UUID(session_id)))
        if existing is not None:
            existing.status = AllocationStatus.FAILED
            existing.failure_reason = reason
            await db.commit()


@celery_app.task(
    name="app.tasks.allocation.run_allocation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=600,
    time_limit=720,
)
def run_allocation_task(self, session_id: str, grn_id: str, brand_id: str) -> dict:
    start = perf_counter()
    logger.info("allocation_started grn=%s session=%s", grn_id, session_id)

    try:
        result = asyncio.run(_run_allocation(session_id, grn_id, brand_id))
        logger.info(
            "allocation_completed grn=%s duration=%.1fs units=%s",
            grn_id,
            perf_counter() - start,
            result.get("total_units"),
        )
        return result
    except SoftTimeLimitExceeded:
        asyncio.run(
            _mark_failed(
                session_id,
                "Allocation generation timed out after 10 minutes. This usually means the dataset is unusually large. Please retry.",
            )
        )
        logger.exception("allocation_timeout grn=%s duration=%.1fs", grn_id, perf_counter() - start)
        raise
    except Exception as exc:
        logger.exception("allocation_failed grn=%s duration=%.1fs", grn_id, perf_counter() - start)
        try:
            countdown = 30 * (self.request.retries + 1)
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            asyncio.run(
                _mark_failed(
                    session_id,
                    f"Allocation failed after 3 attempts. Last error: {str(exc)[:500]}",
                )
            )
            raise
