from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import GRN, GRNLine, SeasonStatus, User, UserRole
from app.routers._helpers import envelope
from app.schemas.grn import GRNCreate
from app.services.workflow_state import advance_season_if_earlier

router = APIRouter(prefix="/api/v1/grns", tags=["grns"])


@router.get("")
async def list_grns(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    offset = (page - 1) * page_size
    total = await db.scalar(select(func.count(GRN.id)).where(GRN.brand_id == current_user.brand_id))
    rows = (
        await db.execute(
            select(GRN)
            .where(GRN.brand_id == current_user.brand_id)
            .order_by(GRN.grn_date.desc())
            .limit(page_size)
            .offset(offset)
        )
    ).scalars().all()
    return envelope(rows, meta={"page": page, "per_page": page_size, "total": int(total or 0)})


@router.get("/{grn_id}")
async def get_grn(
    grn_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    grn = await db.get(GRN, grn_id)
    if grn is None or grn.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "GRN not found"})

    lines = (
        await db.execute(
            select(GRNLine).where(GRNLine.grn_id == grn.id, GRNLine.brand_id == current_user.brand_id)
        )
    ).scalars().all()
    payload = {
        "id": str(grn.id),
        "brand_id": str(grn.brand_id),
        "grn_code": grn.grn_code,
        "grn_date": grn.grn_date.isoformat(),
        "warehouse_id": grn.warehouse_id,
        "supplier_name": grn.supplier_name,
        "status": grn.status,
        "total_units": grn.total_units,
        "total_skus": grn.total_skus,
        "season_id": str(grn.season_id) if grn.season_id else None,
        "created_at": grn.created_at.isoformat(),
        "updated_at": grn.updated_at.isoformat(),
        "lines": [
            {
                "id": str(line.id),
                "grn_id": str(line.grn_id),
                "brand_id": str(line.brand_id),
                "sku_id": str(line.sku_id),
                "units_received": line.units_received,
                "created_at": line.created_at.isoformat(),
                "updated_at": line.updated_at.isoformat(),
            }
            for line in lines
        ],
    }
    return envelope(payload)


@router.post("")
async def create_grn(
    payload: GRNCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    grn = GRN(
        brand_id=current_user.brand_id,
        grn_code=payload.grn_code,
        grn_date=payload.grn_date,
        warehouse_id=payload.warehouse_id,
        supplier_name=payload.supplier_name,
        season_id=payload.season_id,
        status="RECEIVED",
        created_by=current_user.id,
        total_units=sum(line.units_received for line in payload.lines),
        total_skus=len(payload.lines),
    )
    db.add(grn)
    await db.flush()

    for line in payload.lines:
        db.add(
            GRNLine(
                grn_id=grn.id,
                brand_id=current_user.brand_id,
                sku_id=line.sku_id,
                units_received=line.units_received,
            )
        )

    if payload.season_id is not None:
        await advance_season_if_earlier(
            db,
            brand_id=current_user.brand_id,
            season_id=payload.season_id,
            target=SeasonStatus.RECEIVING,
        )

    await db.commit()
    await db.refresh(grn)
    return envelope(grn)
