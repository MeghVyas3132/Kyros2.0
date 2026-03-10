import asyncio
import logging
from datetime import date
from time import perf_counter

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Brand
from app.services.alerts.generator import generate_alerts
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.alert_generation.generate_alerts_task")
def generate_alerts_task() -> dict:
    start = perf_counter()
    logger.info("alert_generation_job_started")

    async def _run() -> dict:
        total_alerts = 0
        async with AsyncSessionLocal() as db:
            brands = (await db.execute(select(Brand).where(Brand.is_active.is_(True)))).scalars().all()
            for brand in brands:
                total_alerts += await generate_alerts(brand.id, date.today(), db)
            await db.commit()
        return {"brands": len(brands), "alerts": total_alerts}

    try:
        result = asyncio.run(_run())
        logger.info(
            "alert_generation_job_completed",
            extra={"duration_seconds": round(perf_counter() - start, 3), **result},
        )
        return result
    except Exception:
        logger.exception(
            "alert_generation_job_failed",
            extra={"duration_seconds": round(perf_counter() - start, 3)},
        )
        raise
