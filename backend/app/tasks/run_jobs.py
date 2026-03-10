import asyncio
from datetime import date

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Brand
from app.services.alerts.generator import generate_alerts
from app.services.inventory.snapshot import build_snapshot_for_brand
from app.services.performance.calculator import build_performance_snapshots


async def run_all_jobs() -> None:
    async with AsyncSessionLocal() as db:
        brands = (await db.execute(select(Brand).where(Brand.is_active.is_(True)))).scalars().all()
        for brand in brands:
            await build_snapshot_for_brand(brand.id, date.today(), db)
            await build_performance_snapshots(brand.id, date.today(), db)
            await generate_alerts(brand.id, date.today(), db)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(run_all_jobs())
    print("All jobs executed")
