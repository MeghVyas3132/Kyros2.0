"""Unit tests for the Groq round-robin client.

We never hit the real Groq API. httpx's MockTransport is plumbed in to
verify:
  - Disabled state returns the deterministic fallback unchanged.
  - Round-robin: keys are rotated across requests.
  - 429 on a key falls through to the next key.
  - All-keys-fail surfaces the deterministic fallback.
  - LRU cache prevents identical prompts from re-hitting the network.
"""
from __future__ import annotations

from typing import Iterator

import httpx
import pytest

from app.services.llm.groq_client import GroqClient


pytestmark = pytest.mark.asyncio


def _make_client_with_transport(
    monkeypatch: pytest.MonkeyPatch,
    keys: str,
    handler,
) -> GroqClient:
    """Build a GroqClient whose internal AsyncClient uses our MockTransport."""
    # Force settings before instantiation.
    from app import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("GROQ_API_KEYS", keys)
    monkeypatch.setenv("LLM_ENABLED", "true")
    client = GroqClient()

    real_async_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("app.services.llm.groq_client.httpx.AsyncClient", _factory)
    return client


async def test_disabled_returns_fallback(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "")
    monkeypatch.setenv("LLM_ENABLED", "true")
    from app import config

    config.get_settings.cache_clear()
    client = GroqClient()
    assert client.enabled is False
    out = await client.narrate(
        system_prompt="sys",
        user_prompt="user",
        fallback="FALLBACK_TEXT",
    )
    assert out == "FALLBACK_TEXT"


async def test_round_robin_rotates_keys(monkeypatch):
    seen_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        seen_keys.append(auth.replace("Bearer ", ""))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    client = _make_client_with_transport(
        monkeypatch, "key-A,key-B,key-C", handler
    )
    # Three calls with distinct prompts (so cache doesn't hide the rotation).
    for i in range(3):
        await client.narrate(
            system_prompt="sys",
            user_prompt=f"prompt-{i}",
            fallback="x",
        )
    assert seen_keys == ["key-A", "key-B", "key-C"]


async def test_429_falls_through_to_next_key(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers.get("authorization", "").replace("Bearer ", "")
        calls.append(key)
        if key == "rate-limited":
            return httpx.Response(429, json={"error": "rate limit"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "succeeded on next key"}}]},
        )

    client = _make_client_with_transport(
        monkeypatch, "rate-limited,good-key", handler
    )
    out = await client.narrate(
        system_prompt="sys",
        user_prompt="prompt",
        fallback="FB",
    )
    assert out == "succeeded on next key"
    assert calls == ["rate-limited", "good-key"]


async def test_all_keys_fail_returns_fallback(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overload"})

    client = _make_client_with_transport(monkeypatch, "k1,k2", handler)
    out = await client.narrate(
        system_prompt="sys",
        user_prompt="prompt",
        fallback="THE_FALLBACK",
    )
    assert out == "THE_FALLBACK"


async def test_cache_hit_skips_network(monkeypatch):
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "cached-result"}}]},
        )

    client = _make_client_with_transport(monkeypatch, "k1", handler)
    out1 = await client.narrate(
        system_prompt="sys", user_prompt="prompt", fallback="x"
    )
    out2 = await client.narrate(
        system_prompt="sys", user_prompt="prompt", fallback="x"
    )
    assert out1 == out2 == "cached-result"
    assert call_count["n"] == 1


async def test_4xx_other_than_429_raises_then_falls_back(monkeypatch):
    """A real auth error (401) is fatal for that key. The narrator catches
    the exception and returns the fallback."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    client = _make_client_with_transport(monkeypatch, "bad-key", handler)
    out = await client.narrate(
        system_prompt="sys",
        user_prompt="prompt",
        fallback="FALLBACK_FROM_401",
    )
    assert out == "FALLBACK_FROM_401"
