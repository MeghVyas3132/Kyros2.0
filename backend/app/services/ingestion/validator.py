from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SKU, Store


@dataclass
class RowError:
    row: int
    field: str
    value: Any
    message: str
    suggested_fix: str | None = None


def _canonical_store_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


SCHEMAS: dict[str, dict[str, Any]] = {
    "SALES": {
        "required": ["store_code", "sku_code", "units_sold"],
        "types": {
            "week_start_date": "date",
            "units_sold": "integer",
            "revenue": "decimal",
            "was_on_promotion": "boolean",
            "was_in_stock": "boolean",
        },
    },
    "INVENTORY": {
        "required": ["snapshot_date", "location_id", "location_type", "sku_code", "units_on_hand"],
        "types": {
            "snapshot_date": "date",
            "units_on_hand": "integer",
            "units_in_transit": "integer",
        },
    },
    "GRN": {
        "required": ["grn_code", "grn_date", "sku_code", "units_received"],
        "types": {
            "grn_date": "date",
            "units_received": "integer",
        },
    },
    "STORE_MASTER": {
        "required": ["store_code", "store_name"],
        "types": {},
    },
    "SKU_MASTER": {
        "required": ["sku_code", "style_code", "style_name", "category", "mrp"],
        "types": {
            "mrp": "decimal",
            "cost_price": "decimal",
        },
    },
    "STORE_GRADES": {
        "required": ["store_name", "product_category", "grade"],
        "types": {},
    },
    "SIZE_GUIDE": {
        "required": ["product_category", "size", "size_type", "min_max_ratio"],
        "types": {
            "min_max_ratio": "integer",
        },
    },
    "BUY_FILE": {
        "required": ["sku_code", "category"],
        "types": {
            "total_buy_qty": "integer",
            "expected_first_allocation_qty": "integer",
        },
    },
    "RESERVATION_TYPES": {
        "required": ["code", "label"],
        "types": {},
    },
}


class UploadValidator:
    def validate_schema(self, df: pd.DataFrame, upload_type: str) -> list[RowError]:
        schema = SCHEMAS[upload_type]
        errors: list[RowError] = []

        missing_columns = [col for col in schema["required"] if col not in df.columns]
        for col in missing_columns:
            errors.append(
                RowError(
                    row=0,
                    field=col,
                    value=None,
                    message=f"Missing required column '{col}'",
                    suggested_fix="Add required column and re-upload",
                )
            )
        if missing_columns:
            return errors

        for idx, row in df.iterrows():
            row_num = idx + 2
            for col in schema["required"]:
                if pd.isna(row.get(col)):
                    errors.append(
                        RowError(
                            row=row_num,
                            field=col,
                            value=None,
                            message=f"Required field '{col}' is empty",
                        )
                    )

        return errors

    async def validate_references(
        self, df: pd.DataFrame, upload_type: str, brand_id: UUID, db: AsyncSession
    ) -> list[RowError]:
        errors: list[RowError] = []
        if upload_type not in {"SALES", "GRN", "INVENTORY", "STORE_GRADES"}:
            return errors

        store_code_map: dict[str, UUID] = {}
        store_name_map: dict[str, UUID] = {}
        if upload_type in {"STORE_GRADES", "SALES"} and "store_name" in df.columns:
            result = await db.execute(select(Store).where(Store.brand_id == brand_id))
            store_name_map = {
                _canonical_store_name(store.store_name): store.id for store in result.scalars().all()
            }

        if "store_code" in df.columns:
            store_codes = sorted({str(s).upper() for s in df["store_code"].dropna().tolist()})
            if store_codes:
                result = await db.execute(
                    select(Store).where(Store.brand_id == brand_id, Store.store_code.in_(store_codes))
                )
                store_code_map = {store.store_code.upper(): store.id for store in result.scalars().all()}
                if upload_type == "SALES":
                    name_result = await db.execute(select(Store).where(Store.brand_id == brand_id))
                    for store in name_result.scalars().all():
                        store_name_map[_canonical_store_name(store.store_name)] = store.id

        sku_code_map: dict[str, UUID] = {}
        sku_style_map: dict[str, UUID] = {}
        if "sku_code" in df.columns:
            sku_codes = sorted({str(s).upper() for s in df["sku_code"].dropna().tolist()})
            if sku_codes:
                result = await db.execute(
                    select(SKU).where(SKU.brand_id == brand_id, SKU.sku_code.in_(sku_codes))
                )
                sku_code_map = {sku.sku_code.upper(): sku.id for sku in result.scalars().all()}
                if upload_type == "SALES":
                    style_result = await db.execute(select(SKU).where(SKU.brand_id == brand_id))
                    for sku in style_result.scalars().all():
                        sku_style_map[sku.style_code.upper()] = sku.id

        for idx, row in df.iterrows():
            row_num = idx + 2
            if upload_type == "STORE_GRADES":
                store_name = str(row.get("store_name", "")).strip()
                if store_name and _canonical_store_name(store_name) not in store_name_map:
                    errors.append(
                        RowError(
                            row=row_num,
                            field="store_name",
                            value=store_name,
                            message=f"Store '{store_name}' not found",
                            suggested_fix="Upload store master first or correct store name",
                        )
                    )
                continue

            if "store_code" in df.columns:
                code = str(row.get("store_code", "")).upper()
                if code and code not in store_code_map and _canonical_store_name(code) not in store_name_map:
                    errors.append(
                        RowError(
                            row=row_num,
                            field="store_code",
                            value=code,
                            message=f"Store '{code}' not found",
                            suggested_fix="Upload/activate store master first",
                        )
                    )

            if "sku_code" in df.columns:
                code = str(row.get("sku_code", "")).upper()
                if code and code not in sku_code_map and code not in sku_style_map:
                    errors.append(
                        RowError(
                            row=row_num,
                            field="sku_code",
                            value=code,
                            message=f"SKU '{code}' not found",
                            suggested_fix="Upload/activate SKU master first",
                        )
                    )

        return errors

    def validate_business_rules(self, df: pd.DataFrame, upload_type: str) -> list[RowError]:
        errors: list[RowError] = []
        today = date.today()

        for idx, row in df.iterrows():
            row_num = idx + 2
            if "units_sold" in df.columns:
                units_sold = row.get("units_sold")
                if (
                    upload_type != "SALES"
                    and units_sold is not None
                    and not pd.isna(units_sold)
                    and float(units_sold) < 0
                ):
                    errors.append(
                        RowError(
                            row=row_num,
                            field="units_sold",
                            value=units_sold,
                            message="units_sold cannot be negative",
                        )
                    )

            if "units_received" in df.columns:
                units_received = row.get("units_received")
                if units_received is not None and not pd.isna(units_received) and int(units_received) <= 0:
                    errors.append(
                        RowError(
                            row=row_num,
                            field="units_received",
                            value=units_received,
                            message="units_received must be > 0",
                        )
                    )

            if "mrp" in df.columns:
                mrp = row.get("mrp")
                if mrp is not None and not pd.isna(mrp) and float(mrp) <= 0:
                    errors.append(
                        RowError(
                            row=row_num,
                            field="mrp",
                            value=mrp,
                            message="mrp must be > 0",
                        )
                    )

            if "min_max_ratio" in df.columns:
                ratio = row.get("min_max_ratio")
                if ratio is not None and not pd.isna(ratio):
                    try:
                        if int(float(ratio)) < 0:
                            errors.append(
                                RowError(
                                    row=row_num,
                                    field="min_max_ratio",
                                    value=ratio,
                                    message="min_max_ratio cannot be negative",
                                )
                            )
                    except (TypeError, ValueError):
                        errors.append(
                            RowError(
                                row=row_num,
                                field="min_max_ratio",
                                value=ratio,
                                message="min_max_ratio must be numeric",
                            )
                        )

            for date_field in ["week_start_date", "grn_date", "snapshot_date"]:
                if date_field in df.columns and row.get(date_field) is not None and not pd.isna(
                    row.get(date_field)
                ):
                    if row.get(date_field) > today:
                        errors.append(
                            RowError(
                                row=row_num,
                                field=date_field,
                                value=str(row.get(date_field)),
                                message=f"{date_field} cannot be in the future",
                            )
                        )

            if upload_type == "INVENTORY" and "units_on_hand" in df.columns:
                units_on_hand = row.get("units_on_hand")
                if (
                    units_on_hand is not None
                    and not pd.isna(units_on_hand)
                    and float(units_on_hand) < 0
                ):
                    errors.append(
                        RowError(
                            row=row_num,
                            field="units_on_hand",
                            value=units_on_hand,
                            message="units_on_hand cannot be negative",
                        )
                    )

        return errors
