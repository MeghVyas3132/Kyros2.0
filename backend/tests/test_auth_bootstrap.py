import pytest
from fastapi import HTTPException

from app.routers.auth import _slugify
from app.schemas.auth import BootstrapRequest


def test_slugify_normalizes_brand_slug() -> None:
    assert _slugify("  ACME Retail 2026!  ") == "acme-retail-2026"


def test_slugify_rejects_empty_slug() -> None:
    with pytest.raises(HTTPException) as exc:
        _slugify("   ")
    assert exc.value.status_code == 422


def test_bootstrap_request_requires_strong_minimum_fields() -> None:
    payload = BootstrapRequest(
        brand_name="Acme",
        full_name="Jane Planner",
        email="jane@acme.com",
        password="securepass123",
    )
    assert payload.brand_name == "Acme"
    assert payload.brand_slug is None
