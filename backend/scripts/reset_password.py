import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.utils.security import get_password_hash

async def reset_password():
    async with AsyncSessionLocal() as session:
        try:
            new_pass = get_password_hash("admin123")
            await session.execute(text("UPDATE users SET hashed_password = :p"), {"p": new_pass})
            await session.commit()
            print("Password updated successfully!")
        except Exception as e:
            print(f"Failed to reset password: {e}")

if __name__ == "__main__":
    asyncio.run(reset_password())
