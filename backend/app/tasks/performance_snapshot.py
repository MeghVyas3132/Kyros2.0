import asyncio
import logging
from datetime import date
from time import perf_counter

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Brand
from app.services.performance.calculator import build_performance_snapshots
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.performance_snapshot.build_performance_snapshots")
def build_performance_snapshots_task() -> dict:
    start = perf_counter()
    logger.info("performance_snapshot_job_started")

    async def _run() -> dict:
        total_rows = 0
        async with AsyncSessionLocal() as db:
            brands = (await db.execute(select(Brand).where(Brand.is_active.is_(True)))).scalars().all()
            for brand in brands:
                total_rows += await build_performance_snapshots(brand.id, date.today(), db)
            await db.commit()
        return {"brands": len(brands), "rows": total_rows}

    try:
        result = asyncio.run(_run())
        logger.info(
            "performance_snapshot_job_completed",
            extra={"duration_seconds": round(perf_counter() - start, 3), **result},
        )
        return result
    except Exception:
        logger.exception(
            "performance_snapshot_job_failed",
            extra={"duration_seconds": round(perf_counter() - start, 3)},
        )
        raise
