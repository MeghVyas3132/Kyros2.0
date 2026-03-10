from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import Cluster, User, UserRole
from app.routers._helpers import envelope
from app.schemas.cluster import ClusterCreate, ClusterUpdate

router = APIRouter(prefix="/api/v1/clusters", tags=["clusters"])


@router.get("")
async def list_clusters(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    rows = (
        await db.execute(select(Cluster).where(Cluster.brand_id == current_user.brand_id))
    ).scalars().all()
    return envelope(rows)


@router.post("")
async def create_cluster(
    payload: ClusterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = Cluster(brand_id=current_user.brand_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.put("/{cluster_id}")
async def update_cluster(
    cluster_id: UUID,
    payload: ClusterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = await db.get(Cluster, cluster_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Cluster not found"})

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return envelope(row)
