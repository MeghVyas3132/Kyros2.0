"""Seed the platform's single SUPER_ADMIN account.

Idempotent. Run this once on a fresh database to create:

  brand: shriem-labs (sentinel brand the SUPER_ADMIN belongs to)
  user : admin@shriemlabs.com / qwerty123  (role=SUPER_ADMIN)

The SUPER_ADMIN is the operator who reviews signup requests and approves
new pilot brands. This sentinel brand exists purely because every User row
in the schema requires a brand_id; it carries no operational data.

Re-running is safe:
  - if the brand exists, it's left as-is
  - if the user exists, the password is *not* clobbered (delete the row first
    if you need to reset it; see ``scripts/reset_password.py``)

Usage:
    cd backend
    DATABASE_URL=... python -m scripts.seed_super_admin

Env overrides:
    SUPER_ADMIN_EMAIL    (default: admin@shriemlabs.com)
    SUPER_ADMIN_PASSWORD (default: qwerty123)
    SUPER_ADMIN_NAME     (default: Shriem Labs Admin)
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

from app.models import Brand, BrandSettings, User, UserRole  # noqa: E402
from app.utils.security import get_password_hash  # noqa: E402

SENTINEL_BRAND_SLUG = "shriem-labs"
SENTINEL_BRAND_NAME = "Shriem Labs"
DEFAULT_EMAIL = "admin@shriemlabs.com"
DEFAULT_PASSWORD = "qwerty123"
DEFAULT_FULL_NAME = "Shriem Labs Admin"


async def main() -> None:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev",
    )
    email = os.environ.get("SUPER_ADMIN_EMAIL", DEFAULT_EMAIL).lower().strip()
    password = os.environ.get("SUPER_ADMIN_PASSWORD", DEFAULT_PASSWORD)
    full_name = os.environ.get("SUPER_ADMIN_NAME", DEFAULT_FULL_NAME).strip()

    engine = create_async_engine(db_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[seed] Target DB: {db_url.split('@')[-1]}")
    async with sf() as db:
        brand = (
            await db.execute(select(Brand).where(Brand.slug == SENTINEL_BRAND_SLUG))
        ).scalars().first()
        if brand is None:
            brand = Brand(name=SENTINEL_BRAND_NAME, slug=SENTINEL_BRAND_SLUG, is_active=True)
            db.add(brand)
            await db.flush()
            db.add(BrandSettings(brand_id=brand.id, config={"sentinel": True}))
            print(f"[seed] Created brand: {brand.name} (slug={brand.slug})")
        else:
            print(f"[seed] Sentinel brand already present: {brand.name}")

        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalars().first()
        if user is None:
            user = User(
                brand_id=brand.id,
                email=email,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                role=UserRole.SUPER_ADMIN,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"[seed] Created SUPER_ADMIN user: {email}")
        else:
            # Force role to SUPER_ADMIN even if the row pre-existed at a lower
            # level — this is the dedicated platform operator account.
            changed = False
            if user.role != UserRole.SUPER_ADMIN:
                user.role = UserRole.SUPER_ADMIN
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if user.brand_id != brand.id:
                user.brand_id = brand.id
                changed = True
            await db.commit()
            await db.refresh(user)
            print(
                f"[seed] User already exists: {email}"
                + (" (role/active/brand normalized)" if changed else "")
            )

    await engine.dispose()
    print("[seed] Done.")
    print()
    print(f"  Email:    {email}")
    print(f"  Password: {password}")
    print(f"  Role:     SUPER_ADMIN")
    print(f"  Brand:    {SENTINEL_BRAND_NAME} ({SENTINEL_BRAND_SLUG})")


if __name__ == "__main__":
    asyncio.run(main())
