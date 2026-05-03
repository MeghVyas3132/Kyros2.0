"""Tests for the structured override_reason_code on allocation lines.

These bypass the allocation engine — we insert an AllocationSession +
AllocationLine directly and exercise the PATCH endpoint.
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


async def _seed_alloc_line(db, tenant, *, reasoning: dict | None = None) -> tuple[AllocationLine, GRN]:
    """Create the minimum graph needed to PATCH an allocation line."""
    season = await make_season(db, tenant)
    sku = await make_sku(db, tenant)

    store = Store(
        brand_id=tenant.brand_id,
        store_code=f"ST-{uuid.uuid4().hex[:6]}",
        store_name="Test Store",
        city="Mumbai",
        is_active=True,
    )
    db.add(store)
    await db.flush()

    grn = GRN(
        brand_id=tenant.brand_id,
        season_id=season.id,
        grn_code=f"GRN-{uuid.uuid4().hex[:6]}",
        grn_date=date(2026, 4, 10),
    )
    db.add(grn)
    await db.flush()

    grn_line = GRNLine(
        brand_id=tenant.brand_id,
        grn_id=grn.id,
        sku_id=sku.id,
        units_received=500,
    )
    db.add(grn_line)

    session = AllocationSession(
        brand_id=tenant.brand_id,
        grn_id=grn.id,
        season_id=season.id,
        status=AllocationStatus.UNDER_REVIEW,
        engine_version="1.0",
    )
    db.add(session)
    await db.flush()

    line = AllocationLine(
        brand_id=tenant.brand_id,
        session_id=session.id,
        store_id=store.id,
        sku_id=sku.id,
        ai_recommended_qty=20,
        ai_confidence="HIGH",
        ai_reasoning=reasoning or {"tier": 1, "ros_raw": 4.2, "cover_target_weeks": 7},
        final_qty=20,
        was_overridden=False,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return line, grn


async def test_override_with_structured_reason_code(client, tenant, db):
    line, _ = await _seed_alloc_line(db, tenant)
    r = await client.put(
        f"/api/v1/allocation/lines/{line.id}",
        json={
            "final_qty": 12,
            "override_reason_code": "GRADE_DRIFT",
            "override_reason": "Store regraded after rent reset",
            "override_notes": "Confirmed with regional ops.",
        },
        headers=tenant.headers,
    )
    assert r.status_code == 200, r.text

    # Reload the line directly and confirm persistence
    await db.refresh(line)
    assert line.final_qty == 12
    assert line.was_overridden is True
    assert line.override_reason_code is not None
    assert line.override_reason_code.value == "GRADE_DRIFT"
    assert "regraded" in (line.override_reason or "")
    assert line.override_notes == "Confirmed with regional ops."


async def test_override_without_reason_code_still_works(client, tenant, db):
    """Free-text override (legacy path) should still succeed for now."""
    line, _ = await _seed_alloc_line(db, tenant)
    r = await client.put(
        f"/api/v1/allocation/lines/{line.id}",
        json={"final_qty": 15, "override_reason": "manual adjustment"},
        headers=tenant.headers,
    )
    assert r.status_code == 200, r.text
    await db.refresh(line)
    assert line.final_qty == 15
    assert line.was_overridden is True
    assert line.override_reason_code is None


async def test_invalid_override_reason_code_rejected(client, tenant, db):
    line, _ = await _seed_alloc_line(db, tenant)
    r = await client.put(
        f"/api/v1/allocation/lines/{line.id}",
        json={"final_qty": 10, "override_reason_code": "NOT_A_REAL_CODE"},
        headers=tenant.headers,
    )
    # Pydantic enum validation → 422
    assert r.status_code == 422


async def test_override_other_tenants_line_returns_404(client, tenant_a, tenant_b, db):
    line, _ = await _seed_alloc_line(db, tenant_a)
    r = await client.put(
        f"/api/v1/allocation/lines/{line.id}",
        json={"final_qty": 1, "override_reason_code": "OTHER"},
        headers=tenant_b.headers,
    )
    # Either 403 or 404 — both are acceptable isolation responses
    assert r.status_code in (403, 404)


async def test_override_persists_across_session_fetch(client, tenant, db):
    line, _ = await _seed_alloc_line(db, tenant)
    await client.put(
        f"/api/v1/allocation/lines/{line.id}",
        json={
            "final_qty": 8,
            "override_reason_code": "VENDOR_DELAY",
            "override_notes": "Drop-2 delayed 3wk",
        },
        headers=tenant.headers,
    )

    # Fetch session and verify line metadata round-trips through API
    detail = await client.get(
        f"/api/v1/allocation/sessions/{line.session_id}", headers=tenant.headers
    )
    assert detail.status_code == 200
    data = detail.json()["data"]
    lines = data.get("lines") or data.get("session_lines") or []
    line_payload = next(
        (l_ for l_ in lines if str(l_["id"]) == str(line.id)), None
    )
    assert line_payload is not None, "line not found in session detail"
    assert line_payload.get("final_qty") == 8
    assert line_payload.get("override_reason_code") == "VENDOR_DELAY"
