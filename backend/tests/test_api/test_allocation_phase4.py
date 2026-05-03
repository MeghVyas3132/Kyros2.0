"""Phase 4 close-out tests.

Three things this file pins down:

1. Display-capacity enforcement — when ``StoreDisplayCapacity.max_units`` is
   set, the engine must never allocate more units to that (store, category)
   than the cell allows.
2. CSV export round-trip — ``GET /sessions/{id}/export`` returns a parseable
   CSV with the right columns, and the ``include_zero`` toggle filters as
   advertised.
3. Ingestion-season fallback — the ``_resolve_ingestion_season`` helper
   tolerates the post-0009 enum that no longer carries ``ACTIVE`` (regression
   on a real bug fixed during synthetic-pilot bring-up).
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    AllocationLine,
    AllocationSession,
    AllocationStatus,
    GRN,
    GRNLine,
    SalesData,
    SeasonStatus,
    SizeGuide,
    Store,
    StoreDisplayCapacity,
    StoreProductGrade,
)
from app.services.allocation.engine import AllocationEngine
from app.services.ingestion.processor import _resolve_ingestion_season
from tests.conftest import make_season, make_sku


pytestmark = pytest.mark.asyncio


# ─── Phase 4 — capacity enforcement ──────────────────────────────────────────


async def test_display_capacity_caps_unit_allocation(client, tenant, db):
    """Engine must respect StoreDisplayCapacity.max_units when distributing.

    Two stores, one SKU, 100 units in GRN. One store has a tight capacity cell
    (max_units=8). After generation, that store must not exceed 8 units.
    """
    season = await make_season(db, tenant)
    sku = await make_sku(db, tenant, category="Kurtis", size="M")

    tight_store = Store(
        brand_id=tenant.brand_id,
        store_code=f"ST-TIGHT-{uuid.uuid4().hex[:6]}",
        store_name="Tight Capacity Store",
        city="Mumbai",
        is_active=True,
    )
    open_store = Store(
        brand_id=tenant.brand_id,
        store_code=f"ST-OPEN-{uuid.uuid4().hex[:6]}",
        store_name="Open Capacity Store",
        city="Delhi",
        is_active=True,
    )
    db.add_all([tight_store, open_store])
    await db.flush()

    db.add(
        SizeGuide(
            brand_id=tenant.brand_id,
            product_category="Kurtis",
            size="M",
            size_type="PIVOTAL",
            min_max_ratio=1,
            is_size_set=False,
            applies_to_grades="ALL",
            display_order=1,
        )
    )
    await db.flush()

    db.add_all(
        [
            StoreProductGrade(
                brand_id=tenant.brand_id,
                store_id=tight_store.id,
                product_category="Kurtis",
                grade="A",
            ),
            StoreProductGrade(
                brand_id=tenant.brand_id,
                store_id=open_store.id,
                product_category="Kurtis",
                grade="A",
            ),
            StoreDisplayCapacity(
                brand_id=tenant.brand_id,
                store_id=tight_store.id,
                category="Kurtis",
                max_styles=2,
                max_units=8,
            ),
            StoreDisplayCapacity(
                brand_id=tenant.brand_id,
                store_id=open_store.id,
                category="Kurtis",
                max_styles=20,
                max_units=200,
            ),
        ]
    )
    # Give both stores some sales history so the engine has demand signal.
    base_week = date(2026, 1, 5)
    for store in (tight_store, open_store):
        for week in range(8):
            db.add(
                SalesData(
                    brand_id=tenant.brand_id,
                    store_id=store.id,
                    sku_id=sku.id,
                    week_start_date=base_week + timedelta(weeks=week),
                    units_sold=4,
                    revenue=2000.0,
                    was_in_stock=True,
                )
            )
    grn = GRN(
        brand_id=tenant.brand_id,
        season_id=season.id,
        grn_code=f"GRN-CAP-{uuid.uuid4().hex[:6]}",
        grn_date=date(2026, 4, 1),
        status="RECEIVED",
        total_units=100,
        total_skus=1,
    )
    db.add(grn)
    await db.flush()
    db.add(
        GRNLine(
            grn_id=grn.id,
            brand_id=tenant.brand_id,
            sku_id=sku.id,
            units_received=100,
        )
    )
    await db.commit()

    engine = AllocationEngine()
    session = await engine.generate(grn.id, tenant.brand_id, db)
    await db.commit()

    lines = (
        await db.execute(
            select(AllocationLine).where(AllocationLine.session_id == session.id)
        )
    ).scalars().all()
    by_store: dict = {}
    for line in lines:
        by_store[line.store_id] = by_store.get(line.store_id, 0) + int(line.ai_recommended_qty or 0)

    total_allocated = sum(by_store.values())
    assert total_allocated > 0, f"Engine should have allocated something, got lines={[(l.store_id, l.ai_recommended_qty) for l in lines]}"
    assert by_store.get(tight_store.id, 0) <= 8, (
        f"Tight store should not exceed max_units=8, got {by_store.get(tight_store.id)}"
    )
    # And the open store should receive a non-trivial share — proving the engine
    # distributed rather than clipping everything to the tight store's ceiling.
    assert by_store.get(open_store.id, 0) >= 1, by_store


# ─── Phase 4 — CSV export round-trip ─────────────────────────────────────────


async def test_csv_export_returns_parseable_csv_with_correct_columns(client, tenant, db):
    season = await make_season(db, tenant)
    sku = await make_sku(db, tenant, category="Kurtis", size="M")
    store = Store(
        brand_id=tenant.brand_id,
        store_code="ST-CSV",
        store_name="CSV Test Store",
        city="Pune",
        is_active=True,
    )
    db.add(store)
    await db.flush()

    grn = GRN(
        brand_id=tenant.brand_id,
        season_id=season.id,
        grn_code="GRN-CSV-1",
        grn_date=date(2026, 4, 5),
        status="RECEIVED",
        total_units=10,
        total_skus=1,
    )
    db.add(grn)
    await db.flush()
    db.add(GRNLine(grn_id=grn.id, brand_id=tenant.brand_id, sku_id=sku.id, units_received=10))

    session = AllocationSession(
        brand_id=tenant.brand_id,
        grn_id=grn.id,
        season_id=season.id,
        status=AllocationStatus.UNDER_REVIEW,
        engine_version="1.0",
        total_units_recommended=10,
    )
    db.add(session)
    await db.flush()
    db.add(
        AllocationLine(
            brand_id=tenant.brand_id,
            session_id=session.id,
            store_id=store.id,
            sku_id=sku.id,
            ai_recommended_qty=10,
            final_qty=10,
            ai_confidence="HIGH",
            ai_reasoning={"narrative_demand": "test"},
            was_overridden=False,
        )
    )
    # And one zero-quantity line — used to test include_zero filtering.
    other_store = Store(
        brand_id=tenant.brand_id,
        store_code="ST-CSV-Z",
        store_name="Zero Store",
        city="Surat",
        is_active=True,
    )
    db.add(other_store)
    await db.flush()
    db.add(
        AllocationLine(
            brand_id=tenant.brand_id,
            session_id=session.id,
            store_id=other_store.id,
            sku_id=sku.id,
            ai_recommended_qty=0,
            final_qty=0,
            ai_confidence="LOW",
            ai_reasoning={"narrative_demand": "no demand"},
            was_overridden=False,
        )
    )
    await db.commit()

    # Default: include_zero=False — should hide the zero-line.
    r = await client.get(
        f"/api/v1/allocation/sessions/{session.id}/export",
        headers=tenant.headers,
    )
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    rows = list(csv.reader(io.StringIO(r.text)))
    header, *body = rows
    assert header == [
        "GRN Code", "SKU Code", "Style Name", "Size",
        "Store Code", "Store Name", "City", "Quantity",
    ]
    assert all(int(row[7]) > 0 for row in body), "Zero-qty lines should be filtered by default"
    qty_sum = sum(int(row[7]) for row in body)
    assert qty_sum == 10

    # With include_zero=True the zero-row appears.
    r2 = await client.get(
        f"/api/v1/allocation/sessions/{session.id}/export?include_zero=true",
        headers=tenant.headers,
    )
    assert r2.status_code == 200
    body2 = list(csv.reader(io.StringIO(r2.text)))[1:]
    assert any(int(row[7]) == 0 for row in body2)


async def test_csv_export_blocks_other_tenant(client, tenant_a, tenant_b, db):
    season = await make_season(db, tenant_a)
    sku = await make_sku(db, tenant_a)
    grn = GRN(
        brand_id=tenant_a.brand_id,
        season_id=season.id,
        grn_code="GRN-A1",
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

    r = await client.get(
        f"/api/v1/allocation/sessions/{session.id}/export",
        headers=tenant_b.headers,
    )
    assert r.status_code == 404


# ─── Phase 4 — ingestion-season fallback regression ──────────────────────────


async def test_resolve_ingestion_season_falls_back_through_statuses(db, tenant):
    """Regression: prior code referenced SeasonStatus.ACTIVE which no longer
    exists after migration 0009. The resolver must walk the canonical order
    instead and find a season in any pre-season-or-later state."""
    s = await make_season(db, tenant)
    s.status = SeasonStatus.BUYING
    await db.commit()

    found = await _resolve_ingestion_season(db, tenant.brand_id)
    assert found.id == s.id

    # And when the only season is DRAFT, it still resolves.
    s.status = SeasonStatus.DRAFT
    await db.commit()
    found = await _resolve_ingestion_season(db, tenant.brand_id)
    assert found.id == s.id
