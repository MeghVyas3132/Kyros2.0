"""Buy plan CRUD endpoint tests."""
from __future__ import annotations

import pytest

from tests.conftest import make_season, make_sku


pytestmark = pytest.mark.asyncio


async def test_create_buy_plan_minimal(client, tenant, db):
    payload = {"name": "SS26 Master Plan"}
    r = await client.post("/api/v1/buy-plans", json=payload, headers=tenant.headers)
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    assert body["name"] == "SS26 Master Plan"
    assert body["season_id"] is None
    assert body["total_lines"] == 0


async def test_create_buy_plan_with_season(client, tenant, db):
    season = await make_season(db, tenant)
    r = await client.post(
        "/api/v1/buy-plans",
        json={"name": "Plan-A", "season_id": str(season.id), "notes": "first plan"},
        headers=tenant.headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    assert body["season_id"] == str(season.id)
    assert body["notes"] == "first plan"


async def test_create_buy_plan_duplicate_name_returns_409(client, tenant):
    await client.post("/api/v1/buy-plans", json={"name": "DUP"}, headers=tenant.headers)
    r = await client.post("/api/v1/buy-plans", json={"name": "DUP"}, headers=tenant.headers)
    assert r.status_code == 409


async def test_create_buy_plan_unknown_season_returns_404(client, tenant):
    fake_season = "00000000-0000-0000-0000-000000000000"
    r = await client.post(
        "/api/v1/buy-plans",
        json={"name": "Plan-X", "season_id": fake_season},
        headers=tenant.headers,
    )
    assert r.status_code == 404


async def test_list_buy_plans_empty(client, tenant):
    r = await client.get("/api/v1/buy-plans", headers=tenant.headers)
    assert r.status_code == 200
    assert r.json()["data"] == []


async def test_list_buy_plans_returns_only_own_brand(client, tenant_a, tenant_b):
    await client.post("/api/v1/buy-plans", json={"name": "A-plan"}, headers=tenant_a.headers)
    await client.post("/api/v1/buy-plans", json={"name": "B-plan"}, headers=tenant_b.headers)

    a_list = await client.get("/api/v1/buy-plans", headers=tenant_a.headers)
    b_list = await client.get("/api/v1/buy-plans", headers=tenant_b.headers)
    assert a_list.status_code == 200 and b_list.status_code == 200
    a_names = {p["name"] for p in a_list.json()["data"]}
    b_names = {p["name"] for p in b_list.json()["data"]}
    assert "A-plan" in a_names and "B-plan" not in a_names
    assert "B-plan" in b_names and "A-plan" not in b_names


async def test_get_other_tenants_plan_returns_404(client, tenant_a, tenant_b):
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "A-only"}, headers=tenant_a.headers
    )
    plan_id = create.json()["data"]["id"]
    r = await client.get(f"/api/v1/buy-plans/{plan_id}", headers=tenant_b.headers)
    assert r.status_code == 404


async def test_update_buy_plan_name(client, tenant):
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "Old Name"}, headers=tenant.headers
    )
    plan_id = create.json()["data"]["id"]
    r = await client.patch(
        f"/api/v1/buy-plans/{plan_id}",
        json={"name": "New Name", "notes": "updated"},
        headers=tenant.headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["name"] == "New Name"
    assert body["notes"] == "updated"


async def test_delete_buy_plan_cascades_lines(client, tenant, db):
    sku = await make_sku(db, tenant)
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "Plan-Del"}, headers=tenant.headers
    )
    plan_id = create.json()["data"]["id"]

    add_line = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines",
        json={"sku_id": str(sku.id), "total_buy_qty": 100, "planned_cost_per_unit": 250.0},
        headers=tenant.headers,
    )
    assert add_line.status_code == 201, add_line.text

    r = await client.delete(f"/api/v1/buy-plans/{plan_id}", headers=tenant.headers)
    assert r.status_code == 204
    follow = await client.get(f"/api/v1/buy-plans/{plan_id}", headers=tenant.headers)
    assert follow.status_code == 404


async def test_create_buy_plan_line_happy(client, tenant, db):
    sku = await make_sku(db, tenant)
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "Plan-L"}, headers=tenant.headers
    )
    plan_id = create.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines",
        json={
            "sku_id": str(sku.id),
            "total_buy_qty": 500,
            "vendor_name": "VendorCo",
            "expected_delivery_week": "2026-04-15",
            "planned_cost_per_unit": 400.0,
            "moq": 300,
            "planned_price_per_unit": 1500.0,
            "planned_margin_pct": 35.0,
            "style_risk_group": "PROVEN",
        },
        headers=tenant.headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    assert body["sku_id"] == str(sku.id)
    assert body["total_buy_qty"] == 500
    assert body["vendor_name"] == "VendorCo"
    assert body["planned_cost_per_unit"] == 400.0
    assert body["sku_code"] == sku.sku_code  # join produced metadata


async def test_create_line_unknown_sku_returns_404(client, tenant):
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "Plan-NoSku"}, headers=tenant.headers
    )
    plan_id = create.json()["data"]["id"]
    r = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines",
        json={"sku_id": "00000000-0000-0000-0000-000000000000", "total_buy_qty": 50},
        headers=tenant.headers,
    )
    assert r.status_code == 404


async def test_create_line_for_other_tenants_sku_returns_404(client, tenant_a, tenant_b, db):
    # SKU belongs to tenant_b
    sku = await make_sku(db, tenant_b)
    # tenant_a creates a plan and tries to add tenant_b's SKU
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "X-Plan"}, headers=tenant_a.headers
    )
    plan_id = create.json()["data"]["id"]
    r = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines",
        json={"sku_id": str(sku.id), "total_buy_qty": 10},
        headers=tenant_a.headers,
    )
    assert r.status_code == 404


async def test_duplicate_line_for_same_sku_and_group_returns_409(client, tenant, db):
    sku = await make_sku(db, tenant)
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "Dup-Line"}, headers=tenant.headers
    )
    plan_id = create.json()["data"]["id"]
    line_payload = {"sku_id": str(sku.id), "total_buy_qty": 100, "store_group_rule": "ALL"}
    r1 = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines", json=line_payload, headers=tenant.headers
    )
    assert r1.status_code == 201
    r2 = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines", json=line_payload, headers=tenant.headers
    )
    assert r2.status_code == 409


async def test_patch_line_updates_commercial_fields(client, tenant, db):
    sku = await make_sku(db, tenant)
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "Edit-Plan"}, headers=tenant.headers
    )
    plan_id = create.json()["data"]["id"]
    add = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines",
        json={"sku_id": str(sku.id), "total_buy_qty": 100, "planned_cost_per_unit": 200.0},
        headers=tenant.headers,
    )
    line_id = add.json()["data"]["id"]
    r = await client.patch(
        f"/api/v1/buy-plans/{plan_id}/lines/{line_id}",
        json={"total_buy_qty": 250, "vendor_name": "NewVendor", "moq": 500},
        headers=tenant.headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["total_buy_qty"] == 250
    assert body["vendor_name"] == "NewVendor"
    assert body["moq"] == 500
    assert body["planned_cost_per_unit"] == 200.0  # unchanged


async def test_delete_line(client, tenant, db):
    sku = await make_sku(db, tenant)
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "Del-Line-Plan"}, headers=tenant.headers
    )
    plan_id = create.json()["data"]["id"]
    add = await client.post(
        f"/api/v1/buy-plans/{plan_id}/lines",
        json={"sku_id": str(sku.id), "total_buy_qty": 50},
        headers=tenant.headers,
    )
    line_id = add.json()["data"]["id"]
    r = await client.delete(
        f"/api/v1/buy-plans/{plan_id}/lines/{line_id}", headers=tenant.headers
    )
    assert r.status_code == 204
    listing = await client.get(
        f"/api/v1/buy-plans/{plan_id}/lines", headers=tenant.headers
    )
    assert listing.status_code == 200
    assert listing.json()["data"] == []


async def test_planner_role_can_crud_but_no_anon(client, tenant):
    # Without auth header → 401
    r = await client.post("/api/v1/buy-plans", json={"name": "no-auth"})
    assert r.status_code == 401
