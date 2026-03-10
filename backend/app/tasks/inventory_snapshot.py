import asyncio
import logging
from datetime import date
from time import perf_counter
from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Brand
from app.services.inventory.snapshot import build_snapshot_for_brand
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.inventory_snapshot.build_inventory_snapshots")
def build_inventory_snapshots() -> dict:
    start = perf_counter()
    logger.info("inventory_snapshot_job_started")

    async def _run() -> dict:
        total_rows = 0
        async with AsyncSessionLocal() as db:
            brands = (await db.execute(select(Brand).where(Brand.is_active.is_(True)))).scalars().all()
            for brand in brands:
                rows = await build_snapshot_for_brand(brand.id, date.today(), db)
                total_rows += rows
            await db.commit()
        return {"brands": len(brands), "rows": total_rows}

    try:
        result = asyncio.run(_run())
        logger.info(
            "inventory_snapshot_job_completed",
            extra={"duration_seconds": round(perf_counter() - start, 3), **result},
        )
        return result
    except Exception:
        logger.exception(
            "inventory_snapshot_job_failed",
            extra={"duration_seconds": round(perf_counter() - start, 3)},
        )
        raise
