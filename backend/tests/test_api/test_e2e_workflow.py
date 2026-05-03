"""End-to-end smoke test that walks all six pre-season workflow steps.

Goal: regression-detect the *narrative*, not engine internals. We seed
allocation lines directly (the engine is exercised by other tests) and
verify the workflow-state endpoint reports the right step at every
transition.

Steps covered:
  1. Season created
  2. OTB saved
  3. Sales + grades present
  4. Buy plan created (with line)
  5. GRN created (with line + buy-plan link)
  6. Allocation generated + approved
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models import (
    AllocationLine,
    AllocationSession,
    AllocationStatus,
    BuyPlanFile,
    BuyPlanLine,
    GRN,
    GRNLine,
    SalesData,
    SeasonStatus,
    Store,
    StoreProductGrade,
)
from tests.conftest import make_season, make_sku


pytestmark = pytest.mark.asyncio


async def test_full_six_step_workflow(client, tenant, db):
    # ── 1. Season setup ─────────────────────────────────────────────────────
    season = await make_season(db, tenant)
    ws = await client.get(
        f"/api/v1/seasons/{season.id}/workflow-state", headers=tenant.headers
    )
    assert ws.status_code == 200
    state = ws.json()["data"]
    assert state["current_step"] == 2  # OTB is next
    assert state["steps"][0]["is_complete"] is True

    # ── 2. OTB saved ────────────────────────────────────────────────────────
    otb_payload = [
        {
            "category": "Kurtis",
            "month": "2026-04-01",
            "planned_sales": 1_000_000,
            "planned_closing_stock": 200_000,
            "opening_stock": 100_000,
            "on_order": 0,
        }
    ]
    r = await client.post(
        f"/api/v1/seasons/{season.id}/otb", json=otb_payload, headers=tenant.headers
    )
    assert r.status_code == 200

    # State machine should have advanced from DRAFT → PLANNING.
    await db.refresh(season)
    assert season.status == SeasonStatus.PLANNING

    state = (
        await client.get(
            f"/api/v1/seasons/{season.id}/workflow-state", headers=tenant.headers
        )
    ).json()["data"]
    assert state["steps"][1]["is_complete"] is True  # OTB step
    # Step 3 (data uploaded) is the next incomplete one.
    assert state["current_step"] == 3

    # ── 3. Sales + grade data ───────────────────────────────────────────────
    sku = await make_sku(db, tenant, category="Kurtis")
    store = Store(
        brand_id=tenant.brand_id,
        store_code=f"ST-{uuid.uuid4().hex[:6]}",
        store_name="Smoke Store",
        city="Mumbai",
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
            units_sold=10,
            revenue=20000.0,
            was_in_stock=True,
        )
    )
    db.add(
        StoreProductGrade(
            brand_id=tenant.brand_id,
            store_id=store.id,
            product_category="Kurtis",
            grade="A",
        )
    )
    await db.commit()

    state = (
        await client.get(
            f"/api/v1/seasons/{season.id}/workflow-state", headers=tenant.headers
        )
    ).json()["data"]
    assert state["steps"][2]["is_complete"] is True
    assert state["current_step"] == 4

    # ── 4. Buy plan created with one line ───────────────────────────────────
    plan_resp = await client.post(
        "/api/v1/buy-plans",
        json={"name": "E2E-Plan", "season_id": str(season.id)},
        headers=tenant.headers,
    )
    assert plan_resp.status_code == 201
    plan_id = plan_resp.json()["data"]["id"]

    # Workflow state machine should have advanced PLANNING → BUYING.
    await db.refresh(season)
    assert season.status == SeasonStatus.BUYING

    line_resp = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines",
        json={
            "sku_id": str(sku.id),
            "total_buy_qty": 200,
            "planned_cost_per_unit": 400.0,
        },
        headers=tenant.headers,
    )
    assert line_resp.status_code == 201

    # ── 5. GRN created (manual route, with buy_plan_line link) ───────────────
    bp_line_id = line_resp.json()["data"]["id"]
    grn = GRN(
        brand_id=tenant.brand_id,
        season_id=season.id,
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
            buy_plan_line_id=uuid.UUID(bp_line_id),
        )
    )
    await db.commit()

    # ── 6. Allocation: seed session + line directly, then approve ───────────
    session = AllocationSession(
        brand_id=tenant.brand_id,
        grn_id=grn.id,
        season_id=season.id,
        status=AllocationStatus.UNDER_REVIEW,
        engine_version="1.0",
        total_units_recommended=80,
    )
    db.add(session)
    await db.flush()
    line = AllocationLine(
        brand_id=tenant.brand_id,
        session_id=session.id,
        store_id=store.id,
        sku_id=sku.id,
        ai_recommended_qty=80,
        ai_confidence="HIGH",
        ai_reasoning={"tier": 1, "ros_raw": 4.2, "cover_target_weeks": 5},
        final_qty=80,
        was_overridden=False,
    )
    db.add(line)
    await db.commit()

    # Approve.
    approve = await client.post(
        f"/api/v1/allocation/sessions/{session.id}/approve",
        headers=tenant.headers,
    )
    assert approve.status_code == 200, approve.text

    # Final state machine state.
    await db.refresh(session)
    await db.refresh(season)
    assert session.status == AllocationStatus.APPROVED
    assert season.status == SeasonStatus.IN_SEASON

    # And the workflow-state endpoint should report all 6 steps complete.
    state = (
        await client.get(
            f"/api/v1/seasons/{season.id}/workflow-state", headers=tenant.headers
        )
    ).json()["data"]
    assert all(s["is_complete"] for s in state["steps"])
    assert state["next_step"] is None


async def test_state_machine_does_not_regress(client, tenant, db):
    """Once a season is in IN_SEASON, saving more OTB rows must not push
    the status backwards to PLANNING."""
    season = await make_season(db, tenant)
    season.status = SeasonStatus.IN_SEASON
    await db.commit()

    payload = [
        {
            "category": "Tops",
            "month": "2026-04-01",
            "planned_sales": 100,
            "planned_closing_stock": 0,
            "opening_stock": 0,
            "on_order": 0,
        }
    ]
    r = await client.post(
        f"/api/v1/seasons/{season.id}/otb", json=payload, headers=tenant.headers
    )
    assert r.status_code == 200

    await db.refresh(season)
    assert season.status == SeasonStatus.IN_SEASON  # unchanged
