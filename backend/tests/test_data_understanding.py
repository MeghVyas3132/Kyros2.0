from app.services.ingestion.understanding import (
    detect_sheet_type,
    suggest_mapping_with_confidence,
)


def test_detect_sheet_type_for_buy_file_headers() -> None:
    detection = detect_sheet_type(
        sheet_name="SS26 BUY FILE",
        df_columns=[
            "BUYER NAME",
            "VENDOR",
            "STYLE NUMBER",
            "PRODUCT",
            "TOP FABRIC",
            "Store Group",
            "Style Group",
            "SIZE",
            "Total Buy Qty",
            "ECOM Reserved Qty",
        ],
    )
    assert detection.sheet_type == "BUY_FILE"
    assert detection.upload_type == "BUY_FILE"
    assert detection.confidence >= 0.8


def test_detect_sheet_type_for_store_grades_headers() -> None:
    detection = detect_sheet_type(
        sheet_name="Sheet1",
        df_columns=[
            "Region",
            "Store Name",
            "Product",
            "Price Band",
            "Store Grade - Prod Price Band",
        ],
    )
    assert detection.sheet_type == "STORE_GRADES"
    assert detection.upload_type == "STORE_GRADES"
    assert detection.confidence >= 0.75


def test_mapping_with_confidence_flags_missing_required_fields() -> None:
    mapping, _, missing, low_conf = suggest_mapping_with_confidence(
        upload_type="STORE_GRADES",
        df_columns=["Region", "Product", "Band"],
    )
    assert "store_name" in missing
    assert "grade" in missing
    assert mapping.get("product_category") == "Product"
    assert not low_conf


def test_mapping_with_confidence_uses_fuzzy_sales_aliases() -> None:
    mapping, confidence, missing, low_conf = suggest_mapping_with_confidence(
        upload_type="SALES",
        df_columns=["STORE NAME", "STYLE_NUMBER", "SALES QTY", "NET SALES"],
    )
    assert not missing
    assert mapping["store_code"] == "STORE NAME"
    assert mapping["sku_code"] == "STYLE_NUMBER"
    assert mapping["units_sold"] == "SALES QTY"
    assert mapping["revenue"] == "NET SALES"
    assert confidence["store_code"] >= 0.86
    assert not low_conf
