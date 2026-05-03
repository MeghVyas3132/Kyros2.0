"""Groq HTTP client with round-robin API key rotation.

KYROS uses Groq for *narration* — turning structured allocation reasoning,
sanity-check results, and OTB suggestions into 2–3 sentence explanations a
merchandiser can read without decoding JSON.

Design choices
--------------
- **Round-robin keys.** Multiple `GROQ_API_KEYS` are configured (comma-
  separated env var). A monotonic counter picks the next key for every
  outbound request, spreading rate-limit pressure across keys.
- **Retry on rate-limit.** If a key returns HTTP 429 we move to the next
  key (max one full rotation). On 5xx we back off briefly then retry once.
- **Tight timeout.** Default 8 s end-to-end. The narrator is decorative;
  the underlying allocation math is already complete and persisted, so a
  slow LLM must never block the API.
- **Deterministic fallback.** If the LLM is disabled, all keys are
  exhausted, or every attempt fails, the caller receives the supplied
  `fallback` string. KYROS APIs *always* return a usable narration.
- **In-process LRU cache.** Identical prompts are served from cache so a
  popular allocation review screen doesn't burn keys re-narrating the
  same line.

We do NOT use the LLM to make any allocation/buy/OTB *decisions*. It only
narrates pre-computed math. See KYROS-MVP-DOCS/10_ai_role_in_kyros.md.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_LRU_MAX = 1024


class GroqClient:
    """Thread-safe-ish round-robin Groq client.

    All public methods are async and side-effect-free except for the LRU
    cache and the rotating key index. Safe to use as a process-wide
    singleton; not safe across processes (each worker has its own
    counter, which is fine — round-robin spreading at the worker level
    is enough).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._keys: list[str] = self._parse_keys(settings.groq_api_keys)
        self._idx = 0
        self._lock = asyncio.Lock()
        self._cache: "OrderedDict[str, str]" = OrderedDict()

    @staticmethod
    def _parse_keys(raw: str | None) -> list[str]:
        return [k.strip() for k in (raw or "").split(",") if k.strip()]

    # ─── public ──────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return bool(self._settings.llm_enabled and self._keys)

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def reload_keys_if_changed(self) -> dict[str, int | bool]:
        """Re-read GROQ_API_KEYS from current settings. If it differs from
        the keys we cached at construction, swap them in, reset the
        round-robin index, and clear the response cache.

        Used by a Celery beat task and the admin refresh endpoint so a key
        rotation in the env doesn't require a backend restart.
        """
        from app import config

        # Settings is `@lru_cache`d; force a re-read.
        config.get_settings.cache_clear()
        new_settings = config.get_settings()
        new_keys = self._parse_keys(new_settings.groq_api_keys)

        if new_keys == self._keys:
            return {"changed": False, "keys": len(self._keys), "cache_cleared": False}

        cleared = len(self._cache)
        self._keys = new_keys
        self._idx = 0
        self._cache.clear()
        self._settings = new_settings
        logger.info(
            "Groq keys rotated: now %d key(s); cleared %d cached narrations",
            len(new_keys),
            cleared,
        )
        return {"changed": True, "keys": len(new_keys), "cache_cleared": cleared}

    async def narrate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: str,
        max_tokens: int | None = None,
        temperature: float = 0.3,
    ) -> str:
        """Return an LLM-generated narration. Falls back deterministically
        if the LLM is disabled, all keys fail, or any error fires."""
        if not self.enabled:
            return fallback

        cache_key = self._cache_key(system_prompt, user_prompt, max_tokens, temperature)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            text = await self._call_with_rotation(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens or self._settings.groq_max_tokens,
                temperature=temperature,
            )
        except Exception as exc:  # noqa: BLE001 — we *want* to swallow.
            logger.warning("Groq narration failed, using fallback: %s", exc)
            return fallback

        cleaned = text.strip()
        if not cleaned:
            return fallback

        self._cache_put(cache_key, cleaned)
        return cleaned

    # ─── internals ───────────────────────────────────────────────────────────

    async def _next_key(self) -> str:
        async with self._lock:
            key = self._keys[self._idx % len(self._keys)]
            self._idx += 1
            return key

    async def _call_with_rotation(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Try every key once. 429/503 → next key. Other 4xx → raise."""
        last_err: Exception | None = None
        async with httpx.AsyncClient(timeout=self._settings.groq_timeout_seconds) as client:
            for _attempt in range(len(self._keys)):
                key = await self._next_key()
                try:
                    resp = await client.post(
                        f"{self._settings.groq_base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self._settings.groq_model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                    )
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_err = exc
                    continue

                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    last_err = RuntimeError(
                        f"Groq HTTP {resp.status_code} on key {key[:8]}…"
                    )
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Groq returned {resp.status_code}: {resp.text[:200]}"
                    )

                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"Groq returned no choices: {data!r}")
                msg = choices[0].get("message") or {}
                return str(msg.get("content") or "")

        raise RuntimeError(
            f"All {len(self._keys)} Groq keys failed; last_err={last_err!r}"
        )

    # ─── cache ───────────────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(
        system_prompt: str, user_prompt: str, max_tokens: int | None, temperature: float
    ) -> str:
        h = hashlib.sha256()
        h.update(system_prompt.encode("utf-8"))
        h.update(b"\x00")
        h.update(user_prompt.encode("utf-8"))
        h.update(b"\x00")
        h.update(str(max_tokens).encode("utf-8"))
        h.update(b"\x00")
        h.update(f"{temperature:.3f}".encode("utf-8"))
        return h.hexdigest()

    def _cache_get(self, key: str) -> str | None:
        if key not in self._cache:
            return None
        # promote to MRU
        value = self._cache.pop(key)
        self._cache[key] = value
        return value

    def _cache_put(self, key: str, value: str) -> None:
        if key in self._cache:
            self._cache.pop(key)
        self._cache[key] = value
        while len(self._cache) > _LRU_MAX:
            self._cache.popitem(last=False)


# ─── singleton ───────────────────────────────────────────────────────────────

_singleton: GroqClient | None = None


def get_groq_client() -> GroqClient:
    """Process-wide singleton. Created lazily so test fixtures that never
    touch the LLM don't pay the cost."""
    global _singleton
    if _singleton is None:
        _singleton = GroqClient()
    return _singleton


def reset_groq_client_for_tests() -> None:
    """Force re-init — useful after changing env vars in tests."""
    global _singleton
    _singleton = None
