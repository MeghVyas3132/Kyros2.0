from __future__ import annotations

from typing import Any

import pandas as pd


class MappingRequiredError(Exception):
    def __init__(self, upload_type: str, missing_fields: list[str], available_columns: list[str]) -> None:
        self.upload_type = upload_type
        self.missing_fields = missing_fields
        self.available_columns = available_columns
        super().__init__(f"Column mapping required for {upload_type}")


STORE_GRADES_ALIASES: dict[str, list[str]] = {
    "store_name": [
        "store name",
        "store",
        "store_name",
        "outlet name",
        "outlet",
        "location name",
    ],
    "product_category": [
        "product",
        "category",
        "product category",
        "department",
        "dept",
    ],
    "price_band": [
        "price band",
        "price_band",
        "price range",
        "mrp band",
        "price tier",
        "band",
        "priceband",
    ],
    "grade": [
        "grade",
        "store grade",
        "store grade - prod price band",
        "store classification",
        "tier",
        "rating",
        "store tier",
    ],
}

SIZE_GUIDE_ALIASES: dict[str, list[str]] = {
    "product_category": ["product category", "product", "category", "store name"],
    "size": ["size", "size label"],
    "size_type": ["size type", "mandatory", "pivotal", "size classification"],
    "min_max_ratio": ["min / max", "min/max", "ratio", "ratio weight", "min_max_ratio"],
    "is_size_set": ["is size set", "size set", "combined size"],
    "applies_to_grades": ["applies to grades", "min grade to send", "size grade rule"],
    "display_order": ["display order", "order", "sequence"],
}

BUY_FILE_ALIASES: dict[str, list[str]] = {
    "buy_plan_name": ["buy plan name", "buy file", "plan name", "season buy name"],
    "sku_code": ["sku code", "sku", "style number", "style code", "item code"],
    "style_code": ["style code", "style number", "style"],
    "style_name": ["style name", "description", "style description"],
    "category": ["product", "category", "product category", "department"],
    "fabric": ["top fabric", "fabric"],
    "colour": ["standardized colour", "standardized color", "colour", "color", "top colour", "top color"],
    "colour_family": ["colour family", "color family"],
    "price_band": ["price band", "price tier", "mrp band"],
    "mrp": ["mrp", "retail price", "selling price"],
    "size": ["size"],
    "store_group_rule": ["store group", "store_group", "target stores", "store tier"],
    "resolved_min_grade": ["resolved min grade", "min grade"],
    "style_risk_group": ["style group", "risk group", "style risk group"],
    "resolved_risk_level": ["resolved risk level", "risk level"],
    "story": ["story", "collection"],
    "sub_story": ["sub story", "sub-story", "sub collection", "sub collection"],
    "buyer_name": ["buyer name", "buyer"],
    "vendor_name": ["vendor", "vendor name", "supplier"],
    "total_buy_qty": ["total buy qty", "buy qty", "ordered qty", "total quantity"],
    "expected_first_allocation_qty": [
        "total available for replenishment",
        "available for first allocation",
        "expected first allocation qty",
    ],
    "ecom_reserved_qty": ["ecom reserved qty", "ecom qty", "ecom reserve"],
    "ars_reserved_qty": [
        "reserved qty for ars",
        "ars reserved qty",
        "replenishment reserve qty",
    ],
}

RESERVATION_TYPES_ALIASES: dict[str, list[str]] = {
    "code": ["code", "reservation code"],
    "label": ["label", "name", "reservation type"],
    "deducts_from_first_allocation": ["deducts from allocation", "deducts", "deduct from first allocation"],
    "display_order": ["display order", "order", "sequence"],
    "is_active": ["is active", "active"],
}

SALES_ALIASES: dict[str, list[str]] = {
    "store_code": ["store code", "store id", "store", "store name", "store_name"],
    "sku_code": ["sku code", "sku", "style number", "style_number", "style code"],
    "week_start_date": ["week start date", "week_start_date", "date", "week"],
    "units_sold": ["units sold", "units_sold", "sales qty", "sales quantity"],
    "revenue": ["revenue", "net sales", "sales value"],
    "was_on_promotion": ["was_on_promotion", "promotion", "on promotion"],
    "was_in_stock": ["was_in_stock", "in stock"],
}

GRN_ALIASES: dict[str, list[str]] = {
    "grn_code": ["grn code", "grn number", "grn"],
    "grn_date": ["grn date", "received date", "date"],
    "sku_code": ["sku code", "sku", "style number", "style_number", "style code"],
    "units_received": ["units received", "received qty", "grn qty", "quantity received"],
    "warehouse_id": ["warehouse", "warehouse id", "location"],
    "supplier_name": ["supplier", "vendor", "supplier name"],
}

UPLOAD_FIELD_ALIASES: dict[str, dict[str, list[str]]] = {
    "SALES": SALES_ALIASES,
    "GRN": GRN_ALIASES,
    "STORE_GRADES": STORE_GRADES_ALIASES,
    "SIZE_GUIDE": SIZE_GUIDE_ALIASES,
    "BUY_FILE": BUY_FILE_ALIASES,
    "RESERVATION_TYPES": RESERVATION_TYPES_ALIASES,
}

UPLOAD_REQUIRED_FIELDS: dict[str, list[str]] = {
    "SALES": ["store_code", "sku_code", "units_sold"],
    "GRN": ["grn_code", "grn_date", "sku_code", "units_received"],
    "STORE_GRADES": ["store_name", "product_category", "grade"],
    "SIZE_GUIDE": ["product_category", "size", "size_type", "min_max_ratio"],
    "BUY_FILE": ["sku_code", "category"],
    "RESERVATION_TYPES": ["code", "label"],
}


def normalize_column_name(value: str) -> str:
    return value.strip().lower().replace("_", " ")


def available_fields(upload_type: str) -> list[str]:
    aliases = UPLOAD_FIELD_ALIASES.get(upload_type, {})
    return list(aliases.keys())


def detect_column_mapping(df_columns: list[str], upload_type: str) -> dict[str, str]:
    aliases = UPLOAD_FIELD_ALIASES.get(upload_type, {})
    required = UPLOAD_REQUIRED_FIELDS.get(upload_type, [])
    normalized = {normalize_column_name(col): col for col in df_columns}
    mapping: dict[str, str] = {}
    missing_required: list[str] = []

    for semantic_field, candidates in aliases.items():
        chosen = None
        for candidate in candidates:
            candidate_key = normalize_column_name(candidate)
            if candidate_key in normalized:
                chosen = normalized[candidate_key]
                break
        if chosen is not None:
            mapping[semantic_field] = chosen
        elif semantic_field in required:
            missing_required.append(semantic_field)

    if missing_required:
        raise MappingRequiredError(upload_type, missing_required, df_columns)
    return mapping


def validate_manual_mapping(
    mapping: dict[str, Any],
    upload_type: str,
    df_columns: list[str],
) -> dict[str, str]:
    allowed_fields = set(available_fields(upload_type))
    required_fields = set(UPLOAD_REQUIRED_FIELDS.get(upload_type, []))
    available = set(df_columns)
    cleaned: dict[str, str] = {}
    missing_required: list[str] = []

    for key, value in mapping.items():
        if key not in allowed_fields:
            continue
        if not isinstance(value, str):
            continue
        if value not in available:
            continue
        cleaned[key] = value

    for field in required_fields:
        if field not in cleaned:
            missing_required.append(field)

    if missing_required:
        raise MappingRequiredError(upload_type, missing_required, df_columns)
    return cleaned


def resolve_column_mapping(
    upload_type: str,
    df_columns: list[str],
    stored_mapping: dict[str, str] | None,
    manual_mapping: dict[str, str] | None,
) -> dict[str, str]:
    if manual_mapping:
        return validate_manual_mapping(manual_mapping, upload_type, df_columns)
    if stored_mapping:
        try:
            return validate_manual_mapping(stored_mapping, upload_type, df_columns)
        except MappingRequiredError:
            pass
    return detect_column_mapping(df_columns, upload_type)


def apply_column_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    rename_map = {source: target for target, source in mapping.items() if source in df.columns}
    transformed = df.rename(columns=rename_map).copy()
    return transformed
