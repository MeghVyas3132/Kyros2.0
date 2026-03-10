import pytest

from app.services.ingestion.mapping import (
    MappingRequiredError,
    detect_column_mapping,
    resolve_column_mapping,
)


def test_detect_store_grades_mapping_aliases() -> None:
    mapping = detect_column_mapping(
        df_columns=["Store Name", "Product", "Price Band", "Store Grade - Prod Price Band"],
        upload_type="STORE_GRADES",
    )
    assert mapping["store_name"] == "Store Name"
    assert mapping["product_category"] == "Product"
    assert mapping["price_band"] == "Price Band"
    assert mapping["grade"] == "Store Grade - Prod Price Band"


def test_mapping_required_when_required_fields_missing() -> None:
    with pytest.raises(MappingRequiredError) as exc:
        detect_column_mapping(
            df_columns=["Store Name", "Price Band"],
            upload_type="STORE_GRADES",
        )
    assert "product_category" in exc.value.missing_fields or "grade" in exc.value.missing_fields


def test_manual_mapping_overrides_alias_detection() -> None:
    mapping = resolve_column_mapping(
        upload_type="BUY_FILE",
        df_columns=["My SKU", "My Category"],
        stored_mapping=None,
        manual_mapping={"sku_code": "My SKU", "category": "My Category"},
    )
    assert mapping["sku_code"] == "My SKU"
    assert mapping["category"] == "My Category"
