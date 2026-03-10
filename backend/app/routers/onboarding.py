from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import InventoryReservationType, UploadType, User, UserRole
from app.routers._helpers import envelope
from app.schemas.onboarding import (
    ColumnMappingPayload,
    OnboardingSettingsPatch,
    ReservationTypeCreate,
    ReservationTypeUpdate,
)
from app.services.ingestion.mapping import UPLOAD_FIELD_ALIASES
from app.services.settings import get_brand_config, patch_brand_config

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    config = await get_brand_config(db, current_user.brand_id)
    reservation_types = (
        await db.execute(
            select(InventoryReservationType)
            .where(InventoryReservationType.brand_id == current_user.brand_id)
            .order_by(InventoryReservationType.display_order.asc(), InventoryReservationType.code.asc())
        )
    ).scalars().all()
    return envelope(
        {
            "config": config,
            "reservation_types": reservation_types,
            "supported_upload_mappings": sorted(list(UPLOAD_FIELD_ALIASES.keys())),
        }
    )


@router.put("/settings")
async def update_settings(
    payload: OnboardingSettingsPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    updated = await patch_brand_config(db, current_user.brand_id, payload.config_patch)
    await db.commit()
    return envelope({"config": updated})


@router.post("/column-mappings/{upload_type}")
async def save_column_mapping(
    upload_type: UploadType,
    payload: ColumnMappingPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    upload_key = upload_type.value
    if upload_key not in UPLOAD_FIELD_ALIASES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Column mapping is not supported for upload type {upload_key}",
            },
        )

    patch = {"column_mappings": {upload_key: payload.mapping}}
    updated = await patch_brand_config(db, current_user.brand_id, patch)
    await db.commit()
    return envelope({"upload_type": upload_key, "mapping": updated.get("column_mappings", {}).get(upload_key, {})})


@router.get("/reservation-types")
async def list_reservation_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = (
        await db.execute(
            select(InventoryReservationType)
            .where(InventoryReservationType.brand_id == current_user.brand_id)
            .order_by(InventoryReservationType.display_order.asc(), InventoryReservationType.code.asc())
        )
    ).scalars().all()
    return envelope(rows)


@router.post("/reservation-types")
async def create_reservation_type(
    payload: ReservationTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = InventoryReservationType(
        brand_id=current_user.brand_id,
        code=payload.code.strip().upper(),
        label=payload.label.strip(),
        deducts_from_first_allocation=payload.deducts_from_first_allocation,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope(row)


@router.put("/reservation-types/{reservation_type_id}")
async def update_reservation_type(
    reservation_type_id: UUID,
    payload: ReservationTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    row = await db.get(InventoryReservationType, reservation_type_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Reservation type not found"},
        )

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return envelope(row)
