"""Tests for Track A (allocation sanity check) + Track C (OTB suggestion).

Both endpoints emit LLM-narrated text. With LLM_ENABLED but no real keys
(test environment), the narrator returns the deterministic fallback —
which is exactly what we assert against.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models import GRN, GRNLine, SalesData, Store
from tests.conftest import make_season, make_sku


pytestmark = pytest.mark.asyncio


async def _make_grn_with_line(db, tenant, sku, season=None) -> GRN:
    grn = GRN(
        brand_id=tenant.brand_id,
        season_id=season.id if season else None,
        grn_code=f"GRN-{uuid.uuid4().hex[:6]}",
        grn_date=date(2026, 4, 10),
        status="RECEIVED",
        total_units=100,
        total_skus=1,
    )
    db.add(grn)
    await db.flush()
    db.add(
        GRNLine(
            brand_id=tenant.brand_id,
            grn_id=grn.id,
            sku_id=sku.id,
            units_received=100,
        )
    )
    await db.commit()
    return grn


# ── Sanity check ────────────────────────────────────────────────────────────

async def test_sanity_blocks_when_no_sales_history(client, tenant, db):
    season = await make_season(db, tenant)
    sku = await make_sku(db, tenant)
    grn = await _make_grn_with_line(db, tenant, sku, season)

    r = await client.get(
        f"/api/v1/allocation/sanity-check?grn_id={grn.id}", headers=tenant.headers
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["ready"] is False
    assert any("sales history" in b.lower() for b in body["blockers"])
    assert body["facts"]["weeks_of_sales"] == 0
    assert body["narration"]


async def test_sanity_warns_on_thin_data(client, tenant, db):
    season = await make_season(db, tenant)
    sku = await make_sku(db, tenant)
    store = Store(
        brand_id=tenant.brand_id,
        store_code=f"ST-{uuid.uuid4().hex[:6]}",
        store_name="S1",
        is_active=True,
    )
    db.add(store)
    await db.flush()
    # Only 2 weeks of history (< 8 → warn).
    for week_offset in range(2):
        db.add(
            SalesData(
                brand_id=tenant.brand_id,
                store_id=store.id,
                sku_id=sku.id,
                week_start_date=date(2026, 1, 5 + 7 * week_offset),
                units_sold=4,
                revenue=1000.0,
                was_in_stock=True,
            )
        )
    await db.commit()
    grn = await _make_grn_with_line(db, tenant, sku, season)

    r = await client.get(
        f"/api/v1/allocation/sanity-check?grn_id={grn.id}", headers=tenant.headers
    )
    body = r.json()["data"]
    assert body["ready"] is True
    assert any("week" in w.lower() for w in body["warnings"])
    assert body["facts"]["weeks_of_sales"] == 2


async def test_sanity_other_tenant_returns_404(client, tenant_a, tenant_b, db):
    sku_a = await make_sku(db, tenant_a)
    grn_a = await _make_grn_with_line(db, tenant_a, sku_a)
    r = await client.get(
        f"/api/v1/allocation/sanity-check?grn_id={grn_a.id}",
        headers=tenant_b.headers,
    )
    assert r.status_code == 404


# ── OTB suggestion ──────────────────────────────────────────────────────────

async def test_otb_suggest_uses_growth_factor(client, tenant, db):
    season = await make_season(db, tenant)
    sku = await make_sku(db, tenant, category="Kurtis")
    store = Store(
        brand_id=tenant.brand_id,
        store_code=f"ST-{uuid.uuid4().hex[:6]}",
        store_name="S",
        is_active=True,
    )
    db.add(store)
    await db.flush()
    db.add(
        SalesData(
            brand_id=tenant.brand_id,
            store_id=store.id,
            sku_id=sku.id,
            week_start_date=date(2026, 1, 5),
            units_sold=100,
            revenue=200000.0,
            was_in_stock=True,
        )
    )
    await db.commit()

    r = await client.post(
        f"/api/v1/seasons/{season.id}/otb/suggest",
        json={"growth_factor": 1.20},
        headers=tenant.headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    cats = data["categories"]
    kurtis = next(c for c in cats if c["category"] == "Kurtis")
    assert kurtis["last_actual_revenue"] == 200000.0
    # 200,000 × 1.20 = 240,000
    assert abs(kurtis["suggested_planned_sales"] - 240000.0) < 0.01
    assert kurtis["narration"]
    # Total rolls up correctly.
    assert abs(data["totals"]["suggested_planned_sales"] - 240000.0) < 0.01


async def test_otb_suggest_other_tenant_returns_404(client, tenant_a, tenant_b, db):
    season = await make_season(db, tenant_a)
    r = await client.post(
        f"/api/v1/seasons/{season.id}/otb/suggest",
        json={"growth_factor": 1.10},
        headers=tenant_b.headers,
    )
    assert r.status_code == 404


async def test_otb_suggest_validates_growth_factor_range(client, tenant, db):
    season = await make_season(db, tenant)
    r = await client.post(
        f"/api/v1/seasons/{season.id}/otb/suggest",
        json={"growth_factor": 5.0},  # > 3.0 max
        headers=tenant.headers,
    )
    assert r.status_code == 422
