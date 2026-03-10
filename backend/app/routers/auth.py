from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.routers._helpers import envelope
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    validate_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
refresh_token_store: dict[str, str] = {}


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "Invalid credentials"},
        )

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    refresh_token_store[refresh_token] = str(user.id)
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    return envelope(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "brand_id": str(user.brand_id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat(),
            },
        }
    )


@router.post("/refresh")
async def refresh(payload: RefreshRequest) -> dict:
    if payload.refresh_token not in refresh_token_store:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "Refresh token invalidated"},
        )
    validate_refresh_token(payload.refresh_token)
    # refresh token validity and claims already checked above
    user_id = refresh_token_store[payload.refresh_token]
    # TODO: confirm with spec - rotate refresh tokens in persistent store.
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    claims = jwt.get_unverified_claims(payload.refresh_token)
    access_claims = {
        "sub": user_id,
        "brand_id": claims["brand_id"],
        "role": claims["role"],
        "exp": datetime.now(timezone.utc).timestamp() + settings.jwt_access_token_expire_hours * 3600,
    }
    access_token = jwt.encode(access_claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return envelope({"access_token": access_token, "token_type": "bearer"})


@router.post("/logout")
async def logout(payload: LogoutRequest) -> dict:
    refresh_token_store.pop(payload.refresh_token, None)
    return envelope({"ok": True})


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)) -> dict:
    return envelope(
        {
            "id": str(current_user.id),
            "brand_id": str(current_user.brand_id),
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
            "is_active": current_user.is_active,
            "created_at": current_user.created_at.isoformat(),
            "updated_at": current_user.updated_at.isoformat(),
        }
    )
