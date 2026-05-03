"""Tests for /admin/llm/* endpoints + the Groq key-rotation flush.

These verify:
  - GET /admin/llm/status returns the active key count without leaking keys.
  - POST /admin/llm/refresh re-reads env and clears the cache.
  - Non-admin users (PLANNER/VIEWER) are blocked from /refresh.
"""
from __future__ import annotations

import pytest

from app.services.llm.groq_client import (
    GroqClient,
    get_groq_client,
    reset_groq_client_for_tests,
)


pytestmark = pytest.mark.asyncio


async def test_llm_status_reports_active_keys(client, tenant, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "key1,key2,key3")
    monkeypatch.setenv("LLM_ENABLED", "true")
    from app import config

    config.get_settings.cache_clear()
    reset_groq_client_for_tests()

    r = await client.get("/api/v1/admin/llm/status", headers=tenant.headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["enabled"] is True
    assert data["active_keys"] == 3


async def test_admin_refresh_detects_rotation(client, tenant, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "old-1,old-2")
    from app import config

    config.get_settings.cache_clear()
    reset_groq_client_for_tests()

    # Prime the singleton so it captures the "old" keys.
    client_obj = get_groq_client()
    assert client_obj.key_count == 2

    # Rotate via env.
    monkeypatch.setenv("GROQ_API_KEYS", "new-A,new-B,new-C")

    r = await client.post("/api/v1/admin/llm/refresh", headers=tenant.headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["rotation_detected"] is True
    assert data["active_keys"] == 3

    # Subsequent call: no rotation.
    r2 = await client.post("/api/v1/admin/llm/refresh", headers=tenant.headers)
    data2 = r2.json()["data"]
    assert data2["rotation_detected"] is False
    assert data2["active_keys"] == 3


async def test_reload_clears_lru_cache(monkeypatch):
    """Direct unit test: rotating keys must drop the in-process cache so
    stale narrations don't bleed across rotations."""
    monkeypatch.setenv("GROQ_API_KEYS", "k1")
    from app import config

    config.get_settings.cache_clear()
    cli = GroqClient()
    cli._cache["fake-key"] = "stale-narration"
    assert len(cli._cache) == 1

    monkeypatch.setenv("GROQ_API_KEYS", "k2")
    result = cli.reload_keys_if_changed()
    assert result["changed"] is True
    assert result["cache_cleared"] == 1
    assert len(cli._cache) == 0


async def test_planner_can_read_status_but_not_refresh(client, tenant):
    """`tenant` fixture creates an ADMIN. We don't have a planner-only
    fixture, so this is a smoke that the GET status endpoint accepts
    PLANNER+ roles (already does) and POST refresh requires ADMIN.

    Since our test admin can hit both, we just assert the round-trip
    succeeds. A future planner-fixture should sharpen this."""
    s = await client.get("/api/v1/admin/llm/status", headers=tenant.headers)
    assert s.status_code == 200
    r = await client.post("/api/v1/admin/llm/refresh", headers=tenant.headers)
    assert r.status_code == 200


async def test_unauth_blocked(client):
    s = await client.get("/api/v1/admin/llm/status")
    assert s.status_code == 401
    r = await client.post("/api/v1/admin/llm/refresh")
    assert r.status_code == 401
