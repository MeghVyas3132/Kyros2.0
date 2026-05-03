"""Multi-tenant isolation tests.

These verify that tenant A cannot read, modify, or delete tenant B's data
across every planning-flow endpoint that matters for MVP.
"""
from __future__ import annotations

import pytest

from tests.conftest import make_season, make_sku


pytestmark = pytest.mark.asyncio


async def test_seasons_isolated(client, tenant_a, tenant_b, db):
    s_a = await make_season(db, tenant_a, name="A-Season")
    s_b = await make_season(db, tenant_b, name="B-Season")

    list_a = await client.get("/api/v1/seasons", headers=tenant_a.headers)
    list_b = await client.get("/api/v1/seasons", headers=tenant_b.headers)
    a_ids = {row["id"] for row in list_a.json()["data"]}
    b_ids = {row["id"] for row in list_b.json()["data"]}

    assert str(s_a.id) in a_ids
    assert str(s_b.id) in b_ids
    assert str(s_a.id) not in b_ids
    assert str(s_b.id) not in a_ids


async def test_cannot_update_other_tenants_season(client, tenant_a, tenant_b, db):
    s_b = await make_season(db, tenant_b)
    r = await client.put(
        f"/api/v1/seasons/{s_b.id}",
        json={"name": "hijacked"},
        headers=tenant_a.headers,
    )
    assert r.status_code == 404


async def test_cannot_save_otb_for_other_tenants_season(client, tenant_a, tenant_b, db):
    s_b = await make_season(db, tenant_b)
    payload = [{
        "category": "X", "month": "2026-04-01",
        "planned_sales": 1, "planned_closing_stock": 0,
        "opening_stock": 0, "on_order": 0,
    }]
    r = await client.post(
        f"/api/v1/seasons/{s_b.id}/otb", json=payload, headers=tenant_a.headers
    )
    assert r.status_code == 404


async def test_cannot_view_other_tenants_buy_plan(client, tenant_a, tenant_b):
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "Secret-A"}, headers=tenant_a.headers
    )
    pid = create.json()["data"]["id"]

    # B cannot GET it
    r = await client.get(f"/api/v1/buy-plans/{pid}", headers=tenant_b.headers)
    assert r.status_code == 404

    # B cannot list it
    list_b = await client.get("/api/v1/buy-plans", headers=tenant_b.headers)
    b_names = {p["name"] for p in list_b.json()["data"]}
    assert "Secret-A" not in b_names


async def test_cannot_modify_other_tenants_buy_plan(client, tenant_a, tenant_b):
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "A-original"}, headers=tenant_a.headers
    )
    pid = create.json()["data"]["id"]

    patched = await client.patch(
        f"/api/v1/buy-plans/{pid}",
        json={"name": "B-tries-to-rename"},
        headers=tenant_b.headers,
    )
    assert patched.status_code == 404

    deleted = await client.delete(f"/api/v1/buy-plans/{pid}", headers=tenant_b.headers)
    assert deleted.status_code == 404


async def test_cannot_modify_other_tenants_buy_plan_line(client, tenant_a, tenant_b, db):
    sku_a = await make_sku(db, tenant_a)
    create = await client.post(
        "/api/v1/buy-plans", json={"name": "A-LinePlan"}, headers=tenant_a.headers
    )
    pid = create.json()["data"]["id"]
    add = await client.post(
        f"/api/v1/buy-plans/{pid}/lines",
        json={"sku_id": str(sku_a.id), "total_buy_qty": 100},
        headers=tenant_a.headers,
    )
    line_id = add.json()["data"]["id"]

    # B tries to read lines
    r_get = await client.get(
        f"/api/v1/buy-plans/{pid}/lines", headers=tenant_b.headers
    )
    assert r_get.status_code == 404

    # B tries to patch the line
    r_patch = await client.patch(
        f"/api/v1/buy-plans/{pid}/lines/{line_id}",
        json={"total_buy_qty": 99999},
        headers=tenant_b.headers,
    )
    assert r_patch.status_code == 404

    # B tries to delete the line
    r_del = await client.delete(
        f"/api/v1/buy-plans/{pid}/lines/{line_id}", headers=tenant_b.headers
    )
    assert r_del.status_code == 404


async def test_workflow_state_isolated(client, tenant_a, tenant_b, db):
    s_a = await make_season(db, tenant_a)
    r = await client.get(
        f"/api/v1/seasons/{s_a.id}/workflow-state", headers=tenant_b.headers
    )
    assert r.status_code == 404


async def test_unauthenticated_requests_blocked(client):
    """Sanity: every protected route requires auth."""
    routes = [
        ("GET", "/api/v1/seasons"),
        ("GET", "/api/v1/buy-plans"),
        ("POST", "/api/v1/buy-plans"),
    ]
    for method, path in routes:
        if method == "GET":
            r = await client.get(path)
        else:
            r = await client.post(path, json={"name": "x"})
        assert r.status_code == 401, f"{method} {path} should require auth"
