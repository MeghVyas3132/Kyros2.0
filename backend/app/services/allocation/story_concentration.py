from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AllocationLine, BrandSettings, SKU


async def get_story_threshold_from_settings(
    brand_id: UUID,
    db: AsyncSession,
    default: int = 4,
) -> int:
    settings = await db.scalar(
        select(BrandSettings.config).where(BrandSettings.brand_id == brand_id)
    )
    if not isinstance(settings, dict):
        return default

    allocation_cfg = settings.get("allocation")
    if not isinstance(allocation_cfg, dict):
        return default

    raw_threshold = allocation_cfg.get("story_concentration_warn_threshold")
    try:
        threshold = int(raw_threshold)
    except (TypeError, ValueError):
        return default
    return threshold if threshold > 0 else default


async def compute_story_concentration(
    session_id: UUID,
    store_id: UUID,
    brand_id: UUID,
    db: AsyncSession,
) -> list[dict[str, object]]:
    rows = await db.execute(
        select(SKU.story, func.count(AllocationLine.id))
        .join(SKU, SKU.id == AllocationLine.sku_id)
        .where(
            AllocationLine.session_id == session_id,
            AllocationLine.store_id == store_id,
            AllocationLine.brand_id == brand_id,
        )
        .group_by(SKU.story)
    )

    threshold = await get_story_threshold_from_settings(
        brand_id=brand_id,
        db=db,
        default=4,
    )
    concentration: list[dict[str, object]] = []
    for story, count in rows.all():
        if not story:
            continue
        style_count = int(count)
        concentration.append(
            {
                "story": story,
                "style_count": style_count,
                "is_high": style_count > threshold,
            }
        )

    concentration.sort(key=lambda item: int(item["style_count"]), reverse=True)
    return concentration
