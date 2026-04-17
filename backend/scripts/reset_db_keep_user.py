import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def reset_db():
    print("Clearing database...")
    async with AsyncSessionLocal() as session:
        # Check we have a brand and user
        res = await session.execute(text("SELECT id, email FROM users LIMIT 1"))
        u = res.fetchone()
        if not u:
            print("No users in db.")
            return

        print(f"Keeping user: {u[1]} (id: {u[0]})")
        
        tables_to_truncate = [
            "uploads",
            "grns",
            "skus",
            "stores",
            "clusters",
            "seasons",
            "buy_plan_files",
            "size_guides",
            "sales_data",
            "inventory_reservation_types",
            "alerts",
        ]
        
        try:
            await session.execute(text(f"TRUNCATE TABLE {', '.join(tables_to_truncate)} CASCADE;"))
            await session.commit()
            print("Database cleared! Only brand, users, and brand_settings remain.")
        except Exception as e:
            print("Failed to truncate due to:", e)
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(reset_db())
