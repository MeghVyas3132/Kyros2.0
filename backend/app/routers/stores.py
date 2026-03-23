from io import BytesIO
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import Store, StoreDisplayCapacity, User, UserRole
from app.routers._helpers import envelope
from app.schemas.store import (
    StoreCapacityCreate,
    StoreCapacityUpdate,
    StoreCreate,
    StoreUpdate,
)

router = APIRouter(prefix="/api/v1/stores", tags=["stores"])


@router.get("")
async def list_stores(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    offset = (page - 1) * page_size
    total = await db.scalar(select(func.count(Store.id)).where(Store.brand_id == current_user.brand_id))
    rows = (
        await db.execute(
            select(Store)
            .where(Store.brand_id == current_user.brand_id)
            .order_by(Store.store_name.asc())
            .limit(page_size)
            .offset(offset)
        )
    ).scalars().all()
    return envelope(rows, meta={"page": page, "per_page": page_size, "total": int(total or 0)})


@router.post("")
async def create_store(
    payload: StoreCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = Store(brand_id=current_user.brand_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.put("/{store_id}")
async def update_store(
    store_id: UUID,
    payload: StoreUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = await db.get(Store, store_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Store not found"})

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.post("/bulk")
async def bulk_stores(
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
                "store_code": str(row["store_code"]).strip().upper(),
                "store_name": row["store_name"],
                "city": row.get("city"),
                "state": row.get("state"),
                "store_type": row.get("store_type"),
                "climate_zone": row.get("climate_zone"),
                "is_active": True,
            }
        )

    if rows:
        stmt = insert(Store).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_stores_brand_store_code",
            set_={
                "store_name": stmt.excluded.store_name,
                "city": stmt.excluded.city,
                "state": stmt.excluded.state,
                "store_type": stmt.excluded.store_type,
                "climate_zone": stmt.excluded.climate_zone,
            },
        )
        await db.execute(stmt)
        await db.commit()

    return envelope({"rows_processed": len(rows)})


@router.get("/display-capacity")
async def list_display_capacity(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    rows = (
        await db.execute(select(StoreDisplayCapacity).where(StoreDisplayCapacity.brand_id == current_user.brand_id))
    ).scalars().all()
    return envelope(rows)


@router.post("/display-capacity")
async def create_display_capacity(
    payload: StoreCapacityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    store = await db.get(Store, payload.store_id)
    if store is None or store.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Store not found"})

    row = StoreDisplayCapacity(brand_id=current_user.brand_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.put("/display-capacity/{capacity_id}")
async def update_display_capacity(
    capacity_id: UUID,
    payload: StoreCapacityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = await db.get(StoreDisplayCapacity, capacity_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Capacity not found"})

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return envelope(row)
