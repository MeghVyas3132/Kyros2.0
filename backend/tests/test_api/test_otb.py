"""OTB save / summary / reconciliation endpoint tests."""
from __future__ import annotations

import pytest

from tests.conftest import make_otb_row, make_season, make_sku


pytestmark = pytest.mark.asyncio


async def test_save_otb_creates_rows(client, tenant, db):
    season = await make_season(db, tenant)
    payload = [
        {
            "category": "Kurtis",
            "month": "2026-04-01",
            "planned_sales": 1000000,
            "planned_closing_stock": 200000,
            "opening_stock": 100000,
            "on_order": 0,
        },
        {
            "category": "Dresses",
            "month": "2026-04-01",
            "planned_sales": 500000,
            "planned_closing_stock": 100000,
            "opening_stock": 50000,
            "on_order": 0,
        },
    ]
    r = await client.post(
        f"/api/v1/seasons/{season.id}/otb",
        json=payload,
        headers=tenant.headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["saved"] == 2

    rows = await client.get(f"/api/v1/seasons/{season.id}/otb", headers=tenant.headers)
    assert rows.status_code == 200
    data = rows.json()["data"]
    assert len(data) == 2


async def test_otb_summary_rolls_up_categories_and_months(client, tenant, db):
    season = await make_season(db, tenant)

    # Two months × two categories
    for cat in ("Kurtis", "Dresses"):
        for month in ("2026-04-01", "2026-05-01"):
            await make_otb_row(
                db, tenant, season,
                category=cat, month=month,
                planned_sales=1_000_000, planned_closing_stock=200_000,
                opening_stock=100_000, on_order=50_000,
            )

    r = await client.get(
        f"/api/v1/seasons/{season.id}/otb/summary", headers=tenant.headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["season_id"] == str(season.id)
    assert {row["category"] for row in data["rows"]} == {"Kurtis", "Dresses"}
    assert {row["month"] for row in data["rows"]} == {"2026-04-01", "2026-05-01"}

    # Each row's otb_value = 1m + 200k - 100k - 50k = 1.05m
    for row in data["rows"]:
        assert abs(row["otb_value"] - 1_050_000.0) < 0.5

    # Totals
    assert abs(data["totals"]["total_otb"] - 4 * 1_050_000.0) < 1.0


async def test_otb_reconciliation_zero_buy_plan(client, tenant, db):
    season = await make_season(db, tenant)
    await make_otb_row(db, tenant, season, category="Kurtis", planned_sales=2_000_000)

    r = await client.get(
        f"/api/v1/seasons/{season.id}/otb/reconciliation", headers=tenant.headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total_committed"] == 0
    assert data["has_overruns"] is False
    assert data["overrun_categories"] == []
    kurtis = next(r for r in data["rows"] if r["category"] == "Kurtis")
    assert kurtis["total_committed"] == 0
    assert kurtis["usage_pct"] == 0


async def test_otb_reconciliation_detects_overrun(client, tenant, db):
    season = await make_season(db, tenant)
    # OTB cap: planned_sales 1M + closing 200k - opening 100k - on_order 0 = 1.1M
    await make_otb_row(
        db, tenant, season, category="Kurtis",
        planned_sales=1_000_000, planned_closing_stock=200_000,
        opening_stock=100_000, on_order=0,
    )

    sku = await make_sku(db, tenant, category="Kurtis")
    plan = await client.post(
        "/api/v1/buy-plans",
        json={"name": "Overrun-Plan", "season_id": str(season.id)},
        headers=tenant.headers,
    )
    plan_id = plan.json()["data"]["id"]

    # 5,000 units × 500 cost = 2.5M (well above 1.1M OTB)
    await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines",
        json={"sku_id": str(sku.id), "total_buy_qty": 5000, "planned_cost_per_unit": 500.0},
        headers=tenant.headers,
    )

    r = await client.get(
        f"/api/v1/seasons/{season.id}/otb/reconciliation", headers=tenant.headers
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["has_overruns"] is True
    assert "Kurtis" in data["overrun_categories"]
    kurtis = next(row for row in data["rows"] if row["category"] == "Kurtis")
    assert kurtis["is_overrun"] is True
    assert kurtis["total_committed"] == 2_500_000.0
    assert kurtis["usage_pct"] > 100


async def test_otb_summary_for_other_tenant_returns_404(client, tenant_a, tenant_b, db):
    season = await make_season(db, tenant_a)
    r = await client.get(
        f"/api/v1/seasons/{season.id}/otb/summary", headers=tenant_b.headers
    )
    assert r.status_code == 404


async def test_otb_save_for_other_tenant_returns_404(client, tenant_a, tenant_b, db):
    season = await make_season(db, tenant_a)
    payload = [{
        "category": "Kurtis", "month": "2026-04-01",
        "planned_sales": 100, "planned_closing_stock": 0,
        "opening_stock": 0, "on_order": 0,
    }]
    r = await client.post(
        f"/api/v1/seasons/{season.id}/otb", json=payload, headers=tenant_b.headers
    )
    assert r.status_code == 404
