"""
Ingestion flow map:
1) Resolve reference IDs using preloaded in-memory maps.
2) Never query stores/SKUs inside row loops.
3) Refresh maps after creating missing stores/SKUs.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SKU, Store


def normalize_key(value: object) -> str:
    return str(value or "").strip().upper()


async def build_lookup_maps(
    db: AsyncSession,
    brand_id: UUID,
) -> tuple[dict[str, UUID], dict[str, UUID], dict[str, UUID]]:
    store_result = await db.execute(
        select(Store.store_code, Store.store_name, Store.id).where(Store.brand_id == brand_id)
    )
    store_map: dict[str, UUID] = {}
    store_name_map: dict[str, UUID] = {}
    for store_code, store_name, store_id in store_result.all():
        store_map[normalize_key(store_code)] = store_id
        store_name_map[normalize_key(store_name)] = store_id

    sku_result = await db.execute(
        select(SKU.sku_code, SKU.style_code, SKU.id).where(SKU.brand_id == brand_id)
    )
    sku_map: dict[str, UUID] = {}
    for sku_code, style_code, sku_id in sku_result.all():
        sku_map[normalize_key(sku_code)] = sku_id
        sku_map[normalize_key(style_code)] = sku_id

    return store_map, store_name_map, sku_map
