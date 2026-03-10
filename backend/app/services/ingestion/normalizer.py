from __future__ import annotations

import re

import pandas as pd

DATE_COLUMNS = {"week_start_date", "grn_date", "month", "snapshot_date", "date"}
BOOL_COLUMNS = {"was_on_promotion", "was_in_stock", "is_active"}
NUMERIC_CURRENCY_COLUMNS = {
    "units_sold",
    "units_received",
    "units_on_hand",
    "units_in_transit",
    "revenue",
    "mrp",
    "cost_price",
    "planned_sales",
    "planned_closing_stock",
    "opening_stock",
    "on_order",
    "total_buy_qty",
    "expected_first_allocation_qty",
    "reserved_qty",
    "ecom_reserved_qty",
    "ars_reserved_qty",
    "min_max_ratio",
    "display_order",
}


TRUE_VALUES = {"true", "1", "yes", "y"}
FALSE_VALUES = {"false", "0", "no", "n"}


def _normalize_bool(value: object) -> object:
    if pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return value


def _normalize_numeric(value: object) -> object:
    if pd.isna(value):
        return None
    text = re.sub(r"[₹,]", "", str(value).strip())
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return value


def _parse_date(value: object) -> object:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if not pd.isna(parsed):
            return parsed.date()
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return value
    return parsed.date()


def normalize(df: pd.DataFrame, upload_type: str) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [c.strip() for c in normalized.columns]

    for col in normalized.columns:
        if normalized[col].dtype == "object":
            normalized[col] = normalized[col].astype(str).str.strip()
            normalized[col] = normalized[col].replace({"": pd.NA, "nan": pd.NA})

    for code_col in ["store_code", "sku_code"]:
        if code_col in normalized.columns:
            normalized[code_col] = normalized[code_col].astype(str).str.strip().str.upper()

    for col in DATE_COLUMNS.intersection(set(normalized.columns)):
        normalized[col] = normalized[col].apply(_parse_date)

    for col in BOOL_COLUMNS.intersection(set(normalized.columns)):
        normalized[col] = normalized[col].apply(_normalize_bool)

    for col in NUMERIC_CURRENCY_COLUMNS.intersection(set(normalized.columns)):
        normalized[col] = normalized[col].apply(_normalize_numeric)

    return normalized
