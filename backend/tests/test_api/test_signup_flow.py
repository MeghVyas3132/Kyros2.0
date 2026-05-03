"""End-to-end tests for the SUPER_ADMIN-driven onboarding flow.

Each test isolates itself with a UUID-suffixed brand slug + email pair so we
do not depend on cross-test cleanup. Residue accumulates harmlessly in the
test DB; CI runs a TRUNCATE before the suite if it ever matters.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models import (
    Brand,
    BrandSettings,
    SignupRequest,
    SignupRequestStatus,
    User,
    UserRole,
)
from app.utils.security import create_access_token, get_password_hash


pytestmark = pytest.mark.asyncio


async def _make_super_admin(db) -> tuple[User, dict[str, str]]:
    suffix = uuid.uuid4().hex[:8]
    brand = Brand(name=f"Shriem Labs {suffix}", slug=f"shriem-{suffix}", is_active=True)
    db.add(brand)
    await db.flush()
    db.add(BrandSettings(brand_id=brand.id, config={"sentinel": True}))
    user = User(
        brand_id=brand.id,
        email=f"super-{suffix}@shriemlabs.com",
        hashed_password=get_password_hash("super-pwd-123"),
        full_name="Super Admin",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token(user)}"}


def _signup_payload(suffix: str | None = None, **overrides) -> dict:
    """Build a signup payload with a unique brand_name + email."""
    suffix = suffix or uuid.uuid4().hex[:8]
    base = {
        "brand_name": f"Pilot Co {suffix}",
        "full_name": f"Pilot Person {suffix}",
        "email": f"pilot-{suffix}@example.com",
        "password": "supersecret-1",
    }
    base.update(overrides)
    return base


# ─── /auth/signup ────────────────────────────────────────────────────────────


async def test_signup_creates_pending_request(client, db):
    payload = _signup_payload(company_size="50-100 stores", notes="From a friend.")
    r = await client.post("/api/v1/auth/signup", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "PENDING"

    req = (
        await db.execute(
            select(SignupRequest).where(SignupRequest.email == payload["email"])
        )
    ).scalars().first()
    assert req is not None
    assert req.status == SignupRequestStatus.PENDING
    assert (await db.scalar(select(Brand).where(Brand.slug == req.brand_slug))) is None
    assert (await db.scalar(select(User).where(User.email == payload["email"]))) is None


async def test_signup_rejects_duplicate_email_and_brand(client):
    suffix = uuid.uuid4().hex[:8]
    payload = _signup_payload(suffix)
    r1 = await client.post("/api/v1/auth/signup", json=payload)
    assert r1.status_code == 200, r1.text

    # Same email, different brand → 409.
    r2 = await client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(uuid.uuid4().hex[:8], email=payload["email"]),
    )
    assert r2.status_code == 409
    assert "email" in r2.json()["error"]["message"].lower()

    # Different email, same brand_name → 409.
    r3 = await client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(uuid.uuid4().hex[:8], brand_name=payload["brand_name"]),
    )
    assert r3.status_code == 409
    assert "brand" in r3.json()["error"]["message"].lower()


async def test_login_pending_returns_signup_pending_error(client):
    payload = _signup_payload()
    await client.post("/api/v1/auth/signup", json=payload)

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SIGNUP_PENDING"


# ─── Super-admin queue ──────────────────────────────────────────────────────


async def test_super_admin_can_list_and_approve_request(client, db):
    _, super_headers = await _make_super_admin(db)
    payload = _signup_payload()
    await client.post("/api/v1/auth/signup", json=payload)

    r = await client.get(
        "/api/v1/admin/signup-requests?status=PENDING", headers=super_headers
    )
    assert r.status_code == 200
    rows = r.json()["data"]
    target = next((row for row in rows if row["email"] == payload["email"]), None)
    assert target is not None and target["status"] == "PENDING"

    r = await client.post(
        f"/api/v1/admin/signup-requests/{target['id']}/approve", headers=super_headers
    )
    assert r.status_code == 200, r.text
    approved = r.json()["data"]
    assert approved["status"] == "APPROVED"
    assert approved["created_brand_id"] and approved["created_user_id"]

    # Real Brand + User now exist.
    user = await db.scalar(select(User).where(User.email == payload["email"]))
    assert user is not None and user.role == UserRole.ADMIN

    # And the user can log in.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    assert login.json()["data"]["user"]["role"] == "ADMIN"

    # Re-approve = 409.
    r2 = await client.post(
        f"/api/v1/admin/signup-requests/{target['id']}/approve", headers=super_headers
    )
    assert r2.status_code == 409


async def test_super_admin_can_reject_request(client, db):
    _, super_headers = await _make_super_admin(db)
    payload = _signup_payload()
    await client.post("/api/v1/auth/signup", json=payload)

    target = (
        await db.execute(select(SignupRequest).where(SignupRequest.email == payload["email"]))
    ).scalars().first()

    r = await client.delete(
        f"/api/v1/admin/signup-requests/{target.id}", headers=super_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "REJECTED"

    # Login post-rejection: AUTH_INVALID, *not* SIGNUP_PENDING.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 401
    assert login.json()["error"]["code"] == "AUTH_INVALID"


async def test_admin_role_cannot_access_super_admin_endpoints(client, tenant):
    """A regular brand ADMIN must NOT see other tenants' signup requests."""
    r = await client.get("/api/v1/admin/signup-requests", headers=tenant.headers)
    assert r.status_code == 403
    r = await client.post(
        f"/api/v1/admin/signup-requests/{uuid.uuid4()}/approve", headers=tenant.headers
    )
    assert r.status_code == 403
    r = await client.delete(
        f"/api/v1/admin/signup-requests/{uuid.uuid4()}", headers=tenant.headers
    )
    assert r.status_code == 403


async def test_unauth_cannot_access_super_admin_endpoints(client):
    r = await client.get("/api/v1/admin/signup-requests")
    assert r.status_code == 401
    r = await client.post(f"/api/v1/admin/signup-requests/{uuid.uuid4()}/approve")
    assert r.status_code == 401


# ─── Tenant-block regression ────────────────────────────────────────────────


async def test_super_admin_cannot_run_tenant_endpoints(client, db):
    """Regression for the bring-up bug: a SUPER_ADMIN logged into the sentinel
    brand uploaded a buy file, which trapped the runner in PROCESSING because
    Shriem Labs has no season. Now any tenant-scoped endpoint returns 403 with
    a distinct error code so the planner UI can route the user back to the
    right place instead of failing silently."""
    _, super_headers = await _make_super_admin(db)

    # Picked one PLANNER+ endpoint per dimension: write, ingest, and approval.
    write = await client.post(
        "/api/v1/buy-plans",
        json={"name": "x", "season_id": str(uuid.uuid4())},
        headers=super_headers,
    )
    assert write.status_code == 403
    assert write.json()["error"]["code"] == "SUPER_ADMIN_TENANT_BLOCKED"

    cluster = await client.post(
        "/api/v1/clusters",
        json={"name": "X", "store_ids": []},
        headers=super_headers,
    )
    assert cluster.status_code == 403
    assert cluster.json()["error"]["code"] == "SUPER_ADMIN_TENANT_BLOCKED"

    # Approval endpoint also tenant-scoped.
    alloc_approve = await client.post(
        f"/api/v1/allocation/sessions/{uuid.uuid4()}/approve",
        headers=super_headers,
    )
    assert alloc_approve.status_code == 403
    assert alloc_approve.json()["error"]["code"] == "SUPER_ADMIN_TENANT_BLOCKED"


async def test_super_admin_can_still_read_their_own_status(client, db):
    """Negative space check: SUPER_ADMIN must still hit /auth/me successfully —
    that's how the frontend detects the role and routes them to /super-admin."""
    super_user, super_headers = await _make_super_admin(db)
    r = await client.get("/api/v1/auth/me", headers=super_headers)
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "SUPER_ADMIN"
    assert r.json()["data"]["email"] == super_user.email
