"""
Celery task that runs the allocation engine in the background.
The HTTP endpoint creates a GENERATING session and dispatches this task.
"""
import asyncio
import logging
from time import perf_counter

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
        try:
            session = await engine.generate(UUID(grn_id), UUID(brand_id), db)
            await db.commit()
            return {
                "session_id": str(session.id),
                "status": session.status.value if hasattr(session.status, "value") else str(session.status),
                "total_units": session.total_units_recommended,
            }
        except Exception:
            # Mark session as failed so frontend can show error
            existing = await db.scalar(
                select(AllocationSession).where(AllocationSession.id == UUID(session_id))
            )
            if existing is not None:
                existing.status = AllocationStatus.DRAFT
            await db.commit()
            raise


@celery_app.task(
    name="app.tasks.allocation.run_allocation",
    bind=True,
    max_retries=0,
    time_limit=600,       # hard kill after 10 min
    soft_time_limit=540,  # soft warning at 9 min
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
    except Exception:
        logger.exception(
            "allocation_failed grn=%s duration=%.1fs",
            grn_id,
            perf_counter() - start,
        )
        raise
