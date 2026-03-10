from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import Season, SeasonOTB, User, UserRole
from app.routers._helpers import envelope
from app.schemas.season import OTBInput, SeasonCreate, SeasonUpdate

router = APIRouter(prefix="/api/v1/seasons", tags=["seasons"])


@router.get("")
async def list_seasons(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    rows = (await db.execute(select(Season).where(Season.brand_id == current_user.brand_id))).scalars().all()
    return envelope(rows)


@router.post("")
async def create_season(
    payload: SeasonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = Season(brand_id=current_user.brand_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.put("/{season_id}")
async def update_season(
    season_id: UUID,
    payload: SeasonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = await db.get(Season, season_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Season not found"})

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.get("/{season_id}/otb")
async def get_otb(
    season_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = (
        await db.execute(
            select(SeasonOTB).where(
                SeasonOTB.brand_id == current_user.brand_id, SeasonOTB.season_id == season_id
            )
        )
    ).scalars().all()
    return envelope(rows)


@router.post("/{season_id}/otb")
async def save_otb(
    season_id: UUID,
    payload: list[OTBInput],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    season = await db.get(Season, season_id)
    if season is None or season.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Season not found"})

    for row in payload:
        existing = await db.execute(
            select(SeasonOTB).where(
                SeasonOTB.brand_id == current_user.brand_id,
                SeasonOTB.season_id == season_id,
                SeasonOTB.category == row.category,
                SeasonOTB.month == row.month,
            )
        )
        item = existing.scalar_one_or_none()
        if item is None:
            db.add(
                SeasonOTB(
                    season_id=season_id,
                    brand_id=current_user.brand_id,
                    category=row.category,
                    month=row.month,
                    planned_sales=row.planned_sales,
                    planned_closing_stock=row.planned_closing_stock,
                    opening_stock=row.opening_stock,
                    on_order=row.on_order,
                )
            )
        else:
            item.planned_sales = row.planned_sales
            item.planned_closing_stock = row.planned_closing_stock
            item.opening_stock = row.opening_stock
            item.on_order = row.on_order

    await db.commit()
    return envelope({"saved": len(payload)})
