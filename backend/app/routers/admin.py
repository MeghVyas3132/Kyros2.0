"""Admin-only operational endpoints.

Two scopes live here:

  * ``/api/v1/admin/llm/*`` — platform LLM key management (ADMIN+).
  * ``/api/v1/admin/signup-requests/*`` — super-admin only; the queue used to
    onboard new pilot brands. ``SUPER_ADMIN`` is the only role that can list,
    approve, or reject signup applications, and is the only role allowed to
    create new tenants on the platform.

Auth is enforced with ``require_role``; tenant scoping is irrelevant for
these routes since super-admin operates above the tenant boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models import (
    Brand,
    BrandSettings,
    SignupRequest,
    SignupRequestStatus,
    User,
    UserRole,
)
from app.routers._helpers import envelope
from app.services.llm.groq_client import get_groq_client

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/llm/refresh")
async def refresh_llm_keys(
    _current: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    """Force the Groq client in *this* process to re-read GROQ_API_KEYS.

    Used to propagate a key rotation without restarting the API container.
    Only flushes the worker that handled this request — other uvicorn
    workers will catch up via the celery_beat refresh schedule (default
    every 10 min) or their own /admin/llm/refresh hit.
    """
    client = get_groq_client()
    result = client.reload_keys_if_changed()
    return envelope(
        {
            "active_keys": result.get("keys"),
            "rotation_detected": result.get("changed"),
            "narrations_cleared": result.get("cache_cleared"),
            "llm_enabled": client.enabled,
        }
    )


@router.get("/llm/status")
async def llm_status(
    _current: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    client = get_groq_client()
    return envelope(
        {
            "enabled": client.enabled,
            "active_keys": client.key_count,
        }
    )


# ─── Super-admin: signup-request queue ──────────────────────────────────────


def _request_payload(req: SignupRequest) -> dict:
    return {
        "id": str(req.id),
        "brand_name": req.brand_name,
        "brand_slug": req.brand_slug,
        "full_name": req.full_name,
        "email": req.email,
        "contact_phone": req.contact_phone,
        "company_size": req.company_size,
        "notes": req.notes,
        "status": req.status.value,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
        "reviewed_by": str(req.reviewed_by) if req.reviewed_by else None,
        "created_brand_id": str(req.created_brand_id) if req.created_brand_id else None,
        "created_user_id": str(req.created_user_id) if req.created_user_id else None,
        "created_at": req.created_at.isoformat(),
        "updated_at": req.updated_at.isoformat(),
    }


@router.get("/signup-requests")
async def list_signup_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(require_role(UserRole.SUPER_ADMIN)),
) -> dict:
    """List signup requests for the super-admin queue.

    Filter via ``?status=PENDING|APPROVED|REJECTED``. Default returns all,
    newest first."""
    stmt = select(SignupRequest).order_by(SignupRequest.created_at.desc())
    if status_filter:
        normalized = status_filter.strip().upper()
        try:
            target = SignupRequestStatus(normalized)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": f"Unknown status filter '{status_filter}'.",
                },
            ) from exc
        stmt = stmt.where(SignupRequest.status == target)
    rows = (await db.execute(stmt)).scalars().all()
    return envelope([_request_payload(row) for row in rows])


@router.post("/signup-requests/{request_id}/approve")
async def approve_signup_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_role(UserRole.SUPER_ADMIN)),
) -> dict:
    """Approve a pending signup request: create Brand + BrandSettings + User."""
    req = await db.get(SignupRequest, request_id)
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Signup request not found."},
        )
    if req.status != SignupRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": f"Signup request is already {req.status.value}.",
            },
        )

    # Defensive: re-check the same uniqueness invariants signup() did, in case
    # a different applicant raced past the queue and got onboarded first.
    if await db.scalar(select(Brand.id).where(Brand.slug == req.brand_slug)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Brand slug already taken — pick a new slug or reject this request."},
        )
    if await db.scalar(select(User.id).where(User.email == req.email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Email already in use — reject this request and ask the applicant to use a different address."},
        )

    brand = Brand(name=req.brand_name, slug=req.brand_slug, is_active=True)
    db.add(brand)
    await db.flush()

    db.add(BrandSettings(brand_id=brand.id, config={}))
    user = User(
        brand_id=brand.id,
        email=req.email,
        hashed_password=req.hashed_password,
        full_name=req.full_name,
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    req.status = SignupRequestStatus.APPROVED
    req.reviewed_at = datetime.now(timezone.utc)
    req.reviewed_by = current.id
    req.created_brand_id = brand.id
    req.created_user_id = user.id

    await db.commit()
    await db.refresh(req)
    return envelope(_request_payload(req))


@router.delete("/signup-requests/{request_id}")
async def reject_signup_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_role(UserRole.SUPER_ADMIN)),
) -> dict:
    """Reject a pending signup request.

    The row is *kept* in REJECTED state for audit. To purge entirely use
    ``?hard=true``."""
    req = await db.get(SignupRequest, request_id)
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Signup request not found."},
        )
    if req.status == SignupRequestStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": "Cannot reject an already-approved signup; deactivate the user via the admin console instead.",
            },
        )

    req.status = SignupRequestStatus.REJECTED
    req.reviewed_at = datetime.now(timezone.utc)
    req.reviewed_by = current.id
    await db.commit()
    await db.refresh(req)
    return envelope(_request_payload(req))
