from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Alert, User
from app.routers._helpers import envelope

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    rows = (
        await db.execute(
            select(Alert).where(
                Alert.brand_id == current_user.brand_id,
                Alert.is_dismissed.is_(False),
                Alert.is_read.is_(False),
            )
        )
    ).scalars().all()
    return envelope(rows)


@router.put("/{alert_id}/read")
async def mark_read(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    alert = await db.get(Alert, alert_id)
    if alert is None or alert.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Alert not found"})
    alert.is_read = True
    await db.commit()
    return envelope({"ok": True})


@router.put("/{alert_id}/dismiss")
async def dismiss(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    alert = await db.get(Alert, alert_id)
    if alert is None or alert.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Alert not found"})
    alert.is_dismissed = True
    await db.commit()
    return envelope({"ok": True})


@router.get("/count")
async def count_alerts(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    rows = (
        await db.execute(
            select(
                func.count(Alert.id).label("unread"),
                func.sum(case((Alert.severity == "HIGH", 1), else_=0)).label("high"),
                func.sum(case((Alert.severity == "MEDIUM", 1), else_=0)).label("medium"),
                func.sum(case((Alert.severity == "LOW", 1), else_=0)).label("low"),
            ).where(
                Alert.brand_id == current_user.brand_id,
                Alert.is_dismissed.is_(False),
                Alert.is_read.is_(False),
            )
        )
    ).one()
    return envelope({
        "unread": int(rows.unread or 0),
        "high": int(rows.high or 0),
        "medium": int(rows.medium or 0),
        "low": int(rows.low or 0),
    })
