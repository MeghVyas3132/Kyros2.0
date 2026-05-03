"""Test fixtures for KYROS backend.

Each test gets fresh, isolated tenants (brands + admin users) so tests
don't share state. Tenants are torn down at the end of the test.

Usage:
    async def test_something(client, tenant):
        r = await client.get("/api/v1/seasons", headers=tenant.headers)
        assert r.status_code == 200

    async def test_isolation(client, tenant_a, tenant_b):
        # tenant_a cannot see tenant_b's data
        ...
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date as date_type
from typing import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete as delete_stmt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.database import get_db
from app.main import app as fastapi_app
from app.models import (
    AllocationLine,
    AllocationSession,
    Brand,
    BrandSettings,
    BuyPlanFile,
    BuyPlanLine,
    Cluster,
    GRN,
    GRNLine,
    InventoryReservationType,
    InventoryState,
    SalesData,
    Season,
    SeasonOTB,
    SignupRequest,
    SizeGuide,
    SKU,
    Store,
    StoreDisplayCapacity,
    StoreProductGrade,
    Upload,
    User,
    UserRole,
)
from app.utils.security import create_access_token, get_password_hash

settings = get_settings()
TEST_DATABASE_URL = settings.database_url


# ---------- Engine / sessions ---------- #

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def engine():
    """Function-scoped engine with NullPool — every test gets a fresh
    pool bound to its own event loop. Slower but bulletproof under
    asyncio_mode=auto where each test gets its own loop."""
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def db(engine) -> AsyncIterator[AsyncSession]:
    """Bare DB session (legacy). Prefer `tenant` fixture for new tests."""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.fixture
async def app(engine):
    """FastAPI app with `get_db` overridden to use the function-scoped
    engine on the current event loop. This is what stops the
    'Task attached to a different loop' error chain when tests hit the API."""
    test_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with test_session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    try:
        yield fastapi_app
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the FastAPI app via ASGI transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------- Tenant factory ---------- #

@dataclass
class Tenant:
    """A fully-isolated test tenant: brand + admin user + auth headers."""
    brand_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    headers: dict[str, str]
    label: str  # "a" / "b" / "c" — for debug output


async def _create_tenant(db: AsyncSession, label: str = "x") -> Tenant:
    suffix = uuid.uuid4().hex[:8]
    brand_name = f"Test Brand {label}-{suffix}"
    brand_slug = f"test-{label}-{suffix}"
    email = f"admin-{label}-{suffix}@test.kyros.local"

    brand = Brand(name=brand_name, slug=brand_slug, is_active=True)
    db.add(brand)
    await db.flush()

    db.add(BrandSettings(brand_id=brand.id, config={}))

    user = User(
        brand_id=brand.id,
        email=email,
        hashed_password=get_password_hash("test-password-123"),
        full_name=f"Admin {label.upper()}",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user)
    return Tenant(
        brand_id=brand.id,
        user_id=user.id,
        email=email,
        headers={"Authorization": f"Bearer {token}"},
        label=label,
    )


async def _cleanup_tenant(db: AsyncSession, tenant: Tenant) -> None:
    """Wipe everything owned by this tenant. Order matters: leaf tables first."""
    bid = tenant.brand_id

    # Allocation: lines → sessions
    await db.execute(delete_stmt(AllocationLine).where(AllocationLine.brand_id == bid))
    await db.execute(delete_stmt(AllocationSession).where(AllocationSession.brand_id == bid))
    # GRN: lines → headers
    await db.execute(delete_stmt(GRNLine).where(GRNLine.brand_id == bid))
    await db.execute(delete_stmt(GRN).where(GRN.brand_id == bid))
    # Buy plan: lines → files
    await db.execute(delete_stmt(BuyPlanLine).where(BuyPlanLine.brand_id == bid))
    await db.execute(delete_stmt(BuyPlanFile).where(BuyPlanFile.brand_id == bid))
    # Sales / inventory
    await db.execute(delete_stmt(SalesData).where(SalesData.brand_id == bid))
    await db.execute(delete_stmt(InventoryState).where(InventoryState.brand_id == bid))
    # Store grades, size guide, planogram capacity (must come before Store delete).
    await db.execute(delete_stmt(StoreProductGrade).where(StoreProductGrade.brand_id == bid))
    await db.execute(delete_stmt(StoreDisplayCapacity).where(StoreDisplayCapacity.brand_id == bid))
    await db.execute(delete_stmt(SizeGuide).where(SizeGuide.brand_id == bid))
    # OTB → seasons
    await db.execute(delete_stmt(SeasonOTB).where(SeasonOTB.brand_id == bid))
    await db.execute(delete_stmt(Season).where(Season.brand_id == bid))
    # SKU + Store + Cluster
    await db.execute(delete_stmt(SKU).where(SKU.brand_id == bid))
    await db.execute(delete_stmt(Store).where(Store.brand_id == bid))
    await db.execute(delete_stmt(Cluster).where(Cluster.brand_id == bid))
    # Reservation types, uploads
    await db.execute(delete_stmt(InventoryReservationType).where(InventoryReservationType.brand_id == bid))
    await db.execute(delete_stmt(Upload).where(Upload.brand_id == bid))
    # Brand settings, user, brand. SignupRequests can FK back to users we
    # are about to delete (reviewed_by); detach them first.
    await db.execute(
        delete_stmt(SignupRequest).where(
            (SignupRequest.created_brand_id == bid)
            | SignupRequest.reviewed_by.in_(
                select(User.id).where(User.brand_id == bid)
            )
        )
    )
    await db.execute(delete_stmt(BrandSettings).where(BrandSettings.brand_id == bid))
    await db.execute(delete_stmt(User).where(User.brand_id == bid))
    await db.execute(delete_stmt(Brand).where(Brand.id == bid))
    await db.commit()


@pytest.fixture
async def tenant(db) -> AsyncIterator[Tenant]:
    """A single, fresh tenant. Cleaned up after the test."""
    t = await _create_tenant(db, label="solo")
    try:
        yield t
    finally:
        await _cleanup_tenant(db, t)


@pytest.fixture
async def tenant_a(db) -> AsyncIterator[Tenant]:
    t = await _create_tenant(db, label="a")
    try:
        yield t
    finally:
        await _cleanup_tenant(db, t)


@pytest.fixture
async def tenant_b(db) -> AsyncIterator[Tenant]:
    t = await _create_tenant(db, label="b")
    try:
        yield t
    finally:
        await _cleanup_tenant(db, t)


# ---------- Domain factories (per-tenant) ---------- #

def _to_date(value: str | date_type) -> date_type:
    if isinstance(value, date_type):
        return value
    return date_type.fromisoformat(value)


async def make_season(
    db: AsyncSession,
    tenant: Tenant,
    *,
    name: str = "TEST-SEASON",
    start: str | date_type = "2026-04-01",
    end: str | date_type = "2026-09-30",
) -> Season:
    s = Season(
        brand_id=tenant.brand_id,
        name=f"{name}-{tenant.label}-{uuid.uuid4().hex[:6]}",
        start_date=_to_date(start),
        end_date=_to_date(end),
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def make_sku(
    db: AsyncSession,
    tenant: Tenant,
    *,
    style_code: str | None = None,
    category: str = "Kurtis",
    size: str = "M",
) -> SKU:
    suffix = uuid.uuid4().hex[:6]
    sc = style_code or f"STY-{tenant.label.upper()}-{suffix}"
    sku = SKU(
        brand_id=tenant.brand_id,
        sku_code=f"{sc}-{size}",
        style_code=sc,
        style_name=f"Style {sc}",
        size=size,
        category=category,
        colour="Indigo",
        price_band="MID",
    )
    db.add(sku)
    await db.commit()
    await db.refresh(sku)
    return sku


async def make_otb_row(
    db: AsyncSession,
    tenant: Tenant,
    season: Season,
    *,
    category: str = "Kurtis",
    month: str | date_type = "2026-04-01",
    planned_sales: float = 1_000_000.0,
    planned_closing_stock: float = 200_000.0,
    opening_stock: float = 100_000.0,
    on_order: float = 0.0,
) -> SeasonOTB:
    row = SeasonOTB(
        brand_id=tenant.brand_id,
        season_id=season.id,
        category=category,
        month=_to_date(month),
        planned_sales=planned_sales,
        planned_closing_stock=planned_closing_stock,
        opening_stock=opening_stock,
        on_order=on_order,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
