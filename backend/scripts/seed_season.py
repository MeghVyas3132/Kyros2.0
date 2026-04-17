import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal
import uuid
from datetime import datetime

async def seed_season():
    async with AsyncSessionLocal() as session:
        # Get brand
        res = await session.execute(text("SELECT id FROM brands LIMIT 1"))
        brand_row = res.fetchone()
        if not brand_row:
            print("No brand found")
            return
        brand_id = brand_row[0]
        
        # Insert a season if none exists
        res = await session.execute(text("SELECT id FROM seasons WHERE brand_id = :b"), {"b": brand_id})
        if not res.fetchone():
            season_id = str(uuid.uuid4())
            await session.execute(
                text("""
                INSERT INTO seasons (id, brand_id, name, status, start_date, end_date) 
                VALUES (:id, :b, 'SS26', 'ACTIVE', '2026-01-01', '2026-07-01')
                """),
                {"id": season_id, "b": brand_id}
            )
            await session.commit()
            print("Created default SS26 season!")
        else:
            print("Season already exists")

if __name__ == "__main__":
    asyncio.run(seed_season())
