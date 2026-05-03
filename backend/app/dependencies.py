from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserRole
from app.utils.security import TokenError, parse_uuid, validate_access_token


async def get_current_user(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Authorization token required"},
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = validate_access_token(token)
    except TokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "Invalid token"},
        )

    user_id = parse_uuid(payload["sub"])
    brand_id = parse_uuid(payload["brand_id"])
    result = await db.execute(select(User).where(User.id == user_id, User.brand_id == brand_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "User not found"},
        )
    return user


def require_role(*roles: UserRole) -> Callable[[User], User]:
    """Gate an endpoint to a fixed set of roles.

    Special case: when a route's role list does NOT include ``SUPER_ADMIN``,
    a SUPER_ADMIN caller is rejected with a clear error rather than the
    generic "insufficient role". The platform super-admin is intentionally
    *not* a tenant operator — they manage signups and shouldn't be touching
    brand-scoped buy plans, GRNs, allocations, etc.
    """
    allowed = set(roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            if (
                current_user.role == UserRole.SUPER_ADMIN
                and UserRole.SUPER_ADMIN not in allowed
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "SUPER_ADMIN_TENANT_BLOCKED",
                        "message": (
                            "SUPER_ADMIN cannot run brand-scoped operations. "
                            "Approve a pilot brand and log in as that brand's "
                            "ADMIN/PLANNER instead."
                        ),
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Insufficient role"},
            )
        return current_user

    return dependency


def brand_filter(current_user: User) -> UUID:
    return current_user.brand_id
