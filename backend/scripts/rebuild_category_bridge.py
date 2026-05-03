"""One-shot backfill of ``StoreCategoryDemand`` for every brand in the DB.

Run after deploying migration 0013 to populate the bridge from existing
``SalesData`` rows. Subsequent sales / buy-file uploads keep it fresh
automatically (see ``services/ingestion/processor.py``).

Usage:
    cd backend
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.rebuild_category_bridge
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.models import Brand  # noqa: E402
from app.services.allocation.category_bridge import rebuild_bridge_for_brand  # noqa: E402


async def main() -> None:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev",
    )
    engine = create_async_engine(db_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[bridge] Target DB: {db_url.split('@')[-1]}")
    async with sf() as db:
        brands = (await db.execute(select(Brand))).scalars().all()
        for brand in brands:
            rows = await rebuild_bridge_for_brand(db, brand.id)
            print(f"  {brand.slug:25s} → {rows} bridge rows")
        await db.commit()
    await engine.dispose()
    print("[bridge] Done.")


if __name__ == "__main__":
    asyncio.run(main())
