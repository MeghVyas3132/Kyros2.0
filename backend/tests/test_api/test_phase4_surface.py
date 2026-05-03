"""Phase 4 surface-area smoke tests.

These prove the API surface a planner touches is round-trip safe:
  - Display-capacity CRUD (`/stores/display-capacity`)
  - Story concentration endpoint (`/allocation/sessions/{sid}/stores/{store}/story-concentration`)
  - GRN-scoped allocation listing
  - Sanity-check endpoint after data is in
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models import (
    AllocationLine,
    AllocationSession,
    AllocationStatus,
    GRN,
    GRNLine,
    Store,
)
from tests.conftest import make_season, make_sku


pytestmark = pytest.mark.asyncio


# ─── Display capacity CRUD ──────────────────────────────────────────────────


async def test_display_capacity_crud_round_trip(client, tenant, db):
    store = Store(
        brand_id=tenant.brand_id,
        store_code="ST-CAP",
        store_name="Capacity Store",
        city="Mumbai",
        is_active=True,
    )
    db.add(store)
    await db.commit()

    # Create
    r = await client.post(
        "/api/v1/stores/display-capacity",
        json={
            "store_id": str(store.id),
            "category": "Kurtis",
            "max_styles": 40,
            "max_units": 240,
        },
        headers=tenant.headers,
    )
    assert r.status_code == 200, r.text
    cap_id = r.json()["data"]["id"]

    # List
    r = await client.get("/api/v1/stores/display-capacity", headers=tenant.headers)
    assert r.status_code == 200
    rows = r.json()["data"]
    assert any(row["id"] == cap_id for row in rows)
    assert any(row["category"] == "Kurtis" and row["max_styles"] == 40 for row in rows)

    # Update
    r = await client.put(
        f"/api/v1/stores/display-capacity/{cap_id}",
        json={"max_units": 300},
        headers=tenant.headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["max_units"] == 300


async def test_display_capacity_blocks_other_tenant(client, tenant_a, tenant_b, db):
    store = Store(
        brand_id=tenant_a.brand_id,
        store_code="ST-A",
        store_name="A's Store",
        is_active=True,
    )
    db.add(store)
    await db.commit()

    # B tries to create capacity for A's store
    r = await client.post(
        "/api/v1/stores/display-capacity",
        json={
            "store_id": str(store.id),
            "category": "Tops",
            "max_styles": 10,
            "max_units": 60,
        },
        headers=tenant_b.headers,
    )
    assert r.status_code == 404


# ─── Story concentration smoke ──────────────────────────────────────────────


async def test_story_concentration_endpoint_returns_structured_payload(client, tenant, db):
    season = await make_season(db, tenant)
    skus = [
        await make_sku(db, tenant, style_code=f"STY-{idx}", category="Kurtis", size="M")
        for idx in range(3)
    ]
    # Tag each SKU with a story.
    for idx, sku in enumerate(skus):
        sku.story = "Floral" if idx < 2 else "Classic"
    await db.commit()

    store = Store(
        brand_id=tenant.brand_id,
        store_code="ST-STORY",
        store_name="Story Store",
        city="Bangalore",
        is_active=True,
    )
    db.add(store)
    await db.flush()

    grn = GRN(
        brand_id=tenant.brand_id,
        season_id=season.id,
        grn_code=f"GRN-STORY-{uuid.uuid4().hex[:6]}",
        grn_date=date(2026, 4, 1),
        status="RECEIVED",
        total_units=30,
        total_skus=3,
    )
    db.add(grn)
    await db.flush()
    for sku in skus:
        db.add(GRNLine(grn_id=grn.id, brand_id=tenant.brand_id, sku_id=sku.id, units_received=10))

    session = AllocationSession(
        brand_id=tenant.brand_id,
        grn_id=grn.id,
        season_id=season.id,
        status=AllocationStatus.UNDER_REVIEW,
        engine_version="1.0",
    )
    db.add(session)
    await db.flush()
    for sku in skus:
        db.add(
            AllocationLine(
                brand_id=tenant.brand_id,
                session_id=session.id,
                store_id=store.id,
                sku_id=sku.id,
                ai_recommended_qty=10,
                final_qty=10,
                ai_confidence="HIGH",
                ai_reasoning={"narrative_demand": "ok"},
                was_overridden=False,
            )
        )
    await db.commit()

    r = await client.get(
        f"/api/v1/allocation/sessions/{session.id}/stores/{store.id}/story-concentration",
        headers=tenant.headers,
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    by_story = {row["story"]: row for row in rows}
    assert by_story["Floral"]["style_count"] == 2
    assert by_story["Classic"]["style_count"] == 1
    # `is_high` is derived from BrandSettings threshold (default 4 → both False).
    assert all(row["is_high"] is False for row in rows)


async def test_story_concentration_blocks_other_tenant(client, tenant_a, tenant_b, db):
    season = await make_season(db, tenant_a)
    grn = GRN(
        brand_id=tenant_a.brand_id,
        season_id=season.id,
        grn_code="GRN-X",
        grn_date=date(2026, 4, 1),
        status="RECEIVED",
        total_units=0,
        total_skus=0,
    )
    db.add(grn)
    await db.flush()
    session = AllocationSession(
        brand_id=tenant_a.brand_id,
        grn_id=grn.id,
        season_id=season.id,
        status=AllocationStatus.UNDER_REVIEW,
        engine_version="1.0",
    )
    db.add(session)
    await db.commit()
    fake_store = uuid.uuid4()

    r = await client.get(
        f"/api/v1/allocation/sessions/{session.id}/stores/{fake_store}/story-concentration",
        headers=tenant_b.headers,
    )
    assert r.status_code == 404


# ─── Allocation by-GRN listing ──────────────────────────────────────────────


async def test_allocation_session_by_grn_returns_session(client, tenant, db):
    season = await make_season(db, tenant)
    grn = GRN(
        brand_id=tenant.brand_id,
        season_id=season.id,
        grn_code="GRN-LOOKUP",
        grn_date=date(2026, 4, 1),
        status="RECEIVED",
        total_units=0,
        total_skus=0,
    )
    db.add(grn)
    await db.flush()
    session = AllocationSession(
        brand_id=tenant.brand_id,
        grn_id=grn.id,
        season_id=season.id,
        status=AllocationStatus.UNDER_REVIEW,
        engine_version="1.0",
    )
    db.add(session)
    await db.commit()

    r = await client.get(
        f"/api/v1/allocation/sessions/by-grn/{grn.id}", headers=tenant.headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["id"] == str(session.id)


async def test_allocation_session_by_grn_404s_when_missing(client, tenant):
    r = await client.get(
        f"/api/v1/allocation/sessions/by-grn/{uuid.uuid4()}", headers=tenant.headers
    )
    assert r.status_code == 404
