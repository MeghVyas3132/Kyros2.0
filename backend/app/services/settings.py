from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BrandSettings


def deep_merge(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


async def get_or_create_brand_settings(db: AsyncSession, brand_id: UUID) -> BrandSettings:
    settings = await db.scalar(select(BrandSettings).where(BrandSettings.brand_id == brand_id))
    if settings is None:
        settings = BrandSettings(brand_id=brand_id, config={"simple_mode": True})
        db.add(settings)
        await db.flush()
    return settings


async def get_brand_config(db: AsyncSession, brand_id: UUID) -> dict:
    settings = await get_or_create_brand_settings(db, brand_id)
    config = settings.config
    return config if isinstance(config, dict) else {}


async def patch_brand_config(db: AsyncSession, brand_id: UUID, patch: dict) -> dict:
    settings = await get_or_create_brand_settings(db, brand_id)
    current = settings.config if isinstance(settings.config, dict) else {}
    settings.config = deep_merge(current, patch)
    await db.flush()
    return settings.config
