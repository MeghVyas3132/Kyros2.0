from io import BytesIO
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import SKU, User, UserRole
from app.routers._helpers import envelope
from app.schemas.sku import SKUCreate, SKUUpdate

router = APIRouter(prefix="/api/v1/skus", tags=["skus"])


@router.get("")
async def list_skus(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    offset = (page - 1) * page_size
    total = await db.scalar(select(func.count(SKU.id)).where(SKU.brand_id == current_user.brand_id))
    rows = (
        await db.execute(
            select(SKU)
            .where(SKU.brand_id == current_user.brand_id)
            .order_by(SKU.style_name.asc(), SKU.sku_code.asc())
            .limit(page_size)
            .offset(offset)
        )
    ).scalars().all()
    return envelope(rows, meta={"page": page, "per_page": page_size, "total": int(total or 0)})


@router.post("")
async def create_sku(
    payload: SKUCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = SKU(brand_id=current_user.brand_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.put("/{sku_id}")
async def update_sku(
    sku_id: UUID,
    payload: SKUUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = await db.get(SKU, sku_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "SKU not found"})

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.post("/bulk")
async def bulk_skus(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    content = await file.read()
    df = pd.read_csv(BytesIO(content))
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "brand_id": current_user.brand_id,
                "sku_code": str(row["sku_code"]).strip().upper(),
                "style_code": row["style_code"],
                "style_name": row["style_name"],
                "category": row["category"],
                "sub_category": row.get("sub_category"),
                "fabric": row.get("fabric"),
                "colour": row.get("colour"),
                "colour_family": row.get("colour_family"),
                "price_band": row.get("price_band"),
                "mrp": row.get("mrp"),
                "cost_price": row.get("cost_price"),
                "size": row.get("size"),
                "fit_type": row.get("fit_type"),
                "sku_type": row.get("sku_type") or "FASHION",
                "is_active": True,
            }
        )

    if rows:
        stmt = insert(SKU).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_skus_brand_sku_code",
            set_={
                "style_code": stmt.excluded.style_code,
                "style_name": stmt.excluded.style_name,
                "category": stmt.excluded.category,
                "sub_category": stmt.excluded.sub_category,
                "fabric": stmt.excluded.fabric,
                "colour": stmt.excluded.colour,
                "colour_family": stmt.excluded.colour_family,
                "price_band": stmt.excluded.price_band,
                "mrp": stmt.excluded.mrp,
                "cost_price": stmt.excluded.cost_price,
                "size": stmt.excluded.size,
                "fit_type": stmt.excluded.fit_type,
                "sku_type": stmt.excluded.sku_type,
            },
        )
        await db.execute(stmt)
        await db.commit()

    return envelope({"rows_processed": len(rows)})
