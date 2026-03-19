"""
Seed script to create initial brand, admin user, and default reservation types.
Run: python -m scripts.seed_data
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add the backend root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import AsyncSessionLocal
from app.models import Brand, BrandSettings, InventoryReservationType, User, UserRole
from app.utils.security import get_password_hash
from sqlalchemy import select


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        # ── Brand ──────────────────────────────────────────────
        brand = await db.scalar(select(Brand).where(Brand.slug == "pilot"))
        if brand is None:
            brand = Brand(name="Pilot Brand", slug="pilot", is_active=True)
            db.add(brand)
            await db.flush()
            print(f"✓ Created brand: {brand.name} (id={brand.id})")
        else:
            print(f"· Brand already exists: {brand.name} (id={brand.id})")

        # ── Brand Settings ─────────────────────────────────────
        settings = await db.scalar(
            select(BrandSettings).where(BrandSettings.brand_id == brand.id)
        )
        if settings is None:
            settings = BrandSettings(
                brand_id=brand.id,
                config={
                    "simple_mode": True,
                    "grade_mapping": {
                        "A+ Stores": "A+",
                        "A Stores": "A",
                        "B Stores": "B",
                        "C Stores": "C",
                        "Grade A+": "A+",
                        "Grade A": "A",
                        "Grade B": "B",
                        "Grade C": "C",
                    },
                    "store_group_mapping": {
                        "ALL STORES": "C",
                        "A+, A, B STORES": "B",
                        "A+, A STORES": "A",
                        "A+ STORES": "A+",
                    },
                    "allocation": {
                        "risk_group_mapping": {
                            "SAFE": "SAFE",
                            "MODERATE": "MODERATE",
                            "EXPERIMENTAL": "EXPERIMENTAL",
                        },
                    },
                },
            )
            db.add(settings)
            await db.flush()
            print("✓ Created default brand settings")
        else:
            print("· Brand settings already exist")

        # ── Admin User ────────────────────────────────────────
        admin = await db.scalar(
            select(User).where(User.email == "admin@kyros.ai")
        )
        if admin is None:
            admin = User(
                brand_id=brand.id,
                email="admin@kyros.ai",
                hashed_password=get_password_hash("kyros123"),
                full_name="Kyros Admin",
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            await db.flush()
            print(f"✓ Created admin user: admin@kyros.ai / kyros123")
        else:
            print(f"· Admin user already exists: {admin.email}")

        # ── Planner User ──────────────────────────────────────
        planner = await db.scalar(
            select(User).where(User.email == "planner@kyros.ai")
        )
        if planner is None:
            planner = User(
                brand_id=brand.id,
                email="planner@kyros.ai",
                hashed_password=get_password_hash("kyros123"),
                full_name="Pilot Planner",
                role=UserRole.PLANNER,
                is_active=True,
            )
            db.add(planner)
            await db.flush()
            print(f"✓ Created planner user: planner@kyros.ai / kyros123")
        else:
            print(f"· Planner user already exists: {planner.email}")

        # ── Default Reservation Types ─────────────────────────
        for code, label, deducts in [
            ("ECOM", "E-Commerce Reserve", True),
            ("ARS", "Auto-Replenishment Reserve", True),
        ]:
            existing = await db.scalar(
                select(InventoryReservationType).where(
                    InventoryReservationType.brand_id == brand.id,
                    InventoryReservationType.code == code,
                )
            )
            if existing is None:
                db.add(
                    InventoryReservationType(
                        brand_id=brand.id,
                        code=code,
                        label=label,
                        deducts_from_first_allocation=deducts,
                        display_order=0,
                        is_active=True,
                    )
                )
                print(f"✓ Created reservation type: {code}")
            else:
                print(f"· Reservation type already exists: {code}")

        await db.commit()
        print("\n✅ Seed data complete. Login with admin@kyros.ai / kyros123")


if __name__ == "__main__":
    asyncio.run(seed())
