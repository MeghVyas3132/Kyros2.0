from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.allocation.story_concentration import get_story_threshold_from_settings


class FakeSession:
    def __init__(self, value):
        self._value = value

    async def scalar(self, _query):
        return self._value


@pytest.mark.asyncio
async def test_story_threshold_uses_brand_setting_value() -> None:
    db = FakeSession({"allocation": {"story_concentration_warn_threshold": 6}})
    threshold = await get_story_threshold_from_settings(brand_id=uuid4(), db=db, default=4)
    assert threshold == 6


@pytest.mark.asyncio
async def test_story_threshold_falls_back_to_default() -> None:
    db = FakeSession({})
    threshold = await get_story_threshold_from_settings(brand_id=uuid4(), db=db, default=4)
    assert threshold == 4
