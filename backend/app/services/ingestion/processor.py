from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import hashlib
from pathlib import Path
import re
from typing import Iterable
from uuid import UUID

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BuyPlanFile,
    BuyPlanLine,
    BrandSettings,
    Season,
    SeasonStatus,
    GRN,
    GRNLine,
    GRNLineReservation,
    InventoryReservationType,
    InventoryState,
    SKU,
    SalesData,
    SizeGuide,
    Store,
    StoreProductGrade,
    Upload,
    UploadStatus,
)
from app.config import get_settings
from app.services.ingestion.normalizer import normalize
from app.services.ingestion.validator import RowError, UploadValidator
from app.services.settings import get_brand_config
from app.services.inventory.snapshot import build_snapshot_for_brand, seed_warehouse_inventory
from app.services.performance.calculator import build_performance_snapshots
from app.services.alerts.generator import generate_alerts
from app.utils.csv_parser import dataframe_from_bytes
from app.utils.date_utils import utcnow
from app.utils.s3 import read_upload_file

settings = get_settings()
ERROR_DIR = Path(settings.local_storage_path) / "errors"
ERROR_DIR.mkdir(parents=True, exist_ok=True)
UPSERT_BATCH_SIZE = 1000


def _errors_to_df(errors: list[RowError]) -> pd.DataFrame:
    rows = [
        {
            "row": e.row,
            "field": e.field,
            "value": e.value,
            "message": e.message,
            "suggested_fix": e.suggested_fix,
        }
        for e in errors
    ]
    return pd.DataFrame(rows)


def _error_row_set(errors: list[RowError]) -> set[int]:
    return {e.row for e in errors if e.row > 0}


def _chunked(rows: list[dict], size: int = UPSERT_BATCH_SIZE) -> Iterable[list[dict]]:
    for idx in range(0, len(rows), size):
        yield rows[idx : idx + size]


def _canonical_store_name(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _clean_str(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _build_store_code(store_name: str) -> str:
    canonical = _canonical_store_name(store_name)
    token = re.sub(r"[^A-Z0-9]+", "_", canonical).strip("_")
    if not token:
        token = "STORE"
    digest = hashlib.md5(canonical.encode("utf-8")).hexdigest()[:6].upper()
    return f"{token[:20]}_{digest}"[:30]


def _sales_category(row: pd.Series) -> str:
    return (
        _clean_str(row.get("category"))
        or _clean_str(row.get("DEPARTMENT"))
        or "Uncategorized"
    )


def _sales_size(row: pd.Series) -> str | None:
    return _clean_str(row.get("size")) or _clean_str(row.get("SIZE_FINAL"))


def _derive_season_name(upload: Upload, df: pd.DataFrame) -> str:
    if "buy_plan_name" in df.columns and not df.empty:
        raw_name = df["buy_plan_name"].iloc[0]
        if raw_name is not None and not pd.isna(raw_name):
            candidate = str(raw_name).strip()
            if candidate:
                return candidate[:100]
    stem = Path(upload.filename).stem
    if "__" in stem:
        stem = stem.split("__")[0]
    stem = stem.strip()
    return stem[:100] if stem else "Season 1"


async def _ensure_simple_mode_season(
    db: AsyncSession, brand_id: UUID, upload: Upload, df: pd.DataFrame
) -> Season | None:
    config = await get_brand_config(db, brand_id)
    if not config.get("simple_mode", True):
        return None

    active = await db.scalar(
        select(Season)
        .where(Season.brand_id == brand_id, Season.status == SeasonStatus.ACTIVE)
        .order_by(Season.start_date.desc())
    )
    if active is not None:
        return active

    latest = await db.scalar(
        select(Season).where(Season.brand_id == brand_id).order_by(Season.start_date.desc())
    )
    if latest is not None:
        latest.status = SeasonStatus.ACTIVE
        await db.flush()
        return latest

    today = date.today()
    season = Season(
        brand_id=brand_id,
        name=_derive_season_name(upload, df) or "Season 1",
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=180),
        categories=[],
        status=SeasonStatus.ACTIVE,
    )
    db.add(season)
    await db.flush()
    return season


async def _run_simple_mode_jobs(db: AsyncSession, brand_id: UUID) -> None:
    today = date.today()
    await build_snapshot_for_brand(brand_id, today, db)
    await build_performance_snapshots(brand_id, today, db)
    await generate_alerts(brand_id, today, db)


async def _resolve_maps(
    db: AsyncSession, brand_id: UUID, df: pd.DataFrame
) -> tuple[dict[str, UUID], dict[str, UUID]]:
    store_map: dict[str, UUID] = {}
    if "store_code" in df.columns:
        result = await db.execute(select(Store).where(Store.brand_id == brand_id))
        store_map = {store.store_code.upper(): store.id for store in result.scalars().all()}

    sku_map: dict[str, UUID] = {}
    if "sku_code" in df.columns:
        result = await db.execute(select(SKU).where(SKU.brand_id == brand_id))
        sku_map = {sku.sku_code.upper(): sku.id for sku in result.scalars().all()}

    return store_map, sku_map


async def _resolve_store_name_map(db: AsyncSession, brand_id: UUID) -> dict[str, UUID]:
    result = await db.execute(select(Store).where(Store.brand_id == brand_id))
    return {_canonical_store_name(store.store_name): store.id for store in result.scalars().all()}


async def _bootstrap_stores_from_names(db: AsyncSession, brand_id: UUID, names: list[object]) -> int:
    result = await db.execute(select(Store).where(Store.brand_id == brand_id))
    existing = result.scalars().all()
    known_codes = {store.store_code.upper() for store in existing}
    known_names = {_canonical_store_name(store.store_name) for store in existing}

    rows: list[dict] = []
    for raw_name in names:
        store_name = _clean_str(raw_name)
        if not store_name:
            continue
        canonical_name = _canonical_store_name(store_name)
        if canonical_name in known_names:
            continue

        store_code = _build_store_code(canonical_name)
        suffix = 1
        while store_code.upper() in known_codes:
            store_code = f"{store_code[:24]}_{suffix}"
            suffix += 1

        rows.append(
            {
                "brand_id": brand_id,
                "store_code": store_code.upper(),
                "store_name": store_name,
                "is_active": True,
            }
        )
        known_codes.add(store_code.upper())
        known_names.add(canonical_name)

    inserted = 0
    for batch in _chunked(rows):
        stmt = insert(Store).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_stores_brand_store_code")
        await db.execute(stmt)
        inserted += len(batch)
    return inserted


async def _bootstrap_sales_dimensions(db: AsyncSession, brand_id: UUID, df: pd.DataFrame) -> tuple[int, int]:
    store_rows_inserted = 0
    if "store_code" in df.columns:
        store_rows_inserted = await _bootstrap_stores_from_names(
            db,
            brand_id,
            df["store_code"].dropna().tolist(),
        )

    result = await db.execute(select(SKU).where(SKU.brand_id == brand_id))
    existing_skus = result.scalars().all()
    known_sku_codes = {sku.sku_code.upper() for sku in existing_skus}
    known_style_codes = {sku.style_code.upper() for sku in existing_skus}

    rows_by_sku: dict[str, dict] = {}
    for _, row in df.iterrows():
        raw_code = _clean_str(row.get("sku_code"))
        if not raw_code:
            continue
        sku_code = raw_code.upper()
        if sku_code in known_sku_codes or sku_code in known_style_codes:
            continue
        if sku_code in rows_by_sku:
            continue

        rows_by_sku[sku_code] = {
            "brand_id": brand_id,
            "sku_code": sku_code,
            "style_code": sku_code,
            "style_name": sku_code,
            "category": _sales_category(row),
            "fabric": _clean_str(row.get("MATERIAL")) or _clean_str(row.get("fabric")),
            "colour": _clean_str(row.get("Standardized Colour")) or _clean_str(row.get("colour")),
            "price_band": _clean_str(row.get("PRICEBAND")) or _clean_str(row.get("price_band")),
            "mrp": row.get("MRP") if row.get("MRP") is not None else row.get("mrp"),
            "size": _sales_size(row),
            "sku_type": "FASHION",
            "is_active": True,
        }

    sku_rows_inserted = 0
    rows = list(rows_by_sku.values())
    for batch in _chunked(rows):
        stmt = insert(SKU).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_skus_brand_sku_code",
            set_={
                "category": stmt.excluded.category,
                "fabric": stmt.excluded.fabric,
                "colour": stmt.excluded.colour,
                "price_band": stmt.excluded.price_band,
                "mrp": stmt.excluded.mrp,
                "size": stmt.excluded.size,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
        sku_rows_inserted += len(batch)

    return store_rows_inserted, sku_rows_inserted


async def _bootstrap_dimensions_for_upload(
    db: AsyncSession,
    upload: Upload,
    df: pd.DataFrame,
) -> None:
    if upload.upload_type.value == "STORE_GRADES" and "store_name" in df.columns:
        await _bootstrap_stores_from_names(db, upload.brand_id, df["store_name"].dropna().tolist())
    elif upload.upload_type.value == "SALES":
        await _bootstrap_sales_dimensions(db, upload.brand_id, df)


async def _upsert_sales(db: AsyncSession, brand_id: UUID, upload_id: UUID, df: pd.DataFrame) -> int:
    result = await db.execute(select(Store).where(Store.brand_id == brand_id))
    stores = result.scalars().all()
    store_code_map = {store.store_code.upper(): store.id for store in stores}
    store_name_map = {_canonical_store_name(store.store_name): store.id for store in stores}

    result = await db.execute(select(SKU).where(SKU.brand_id == brand_id))
    skus = result.scalars().all()
    sku_code_map = {sku.sku_code.upper(): sku.id for sku in skus}
    sku_style_map = {sku.style_code.upper(): sku.id for sku in skus}

    default_week_start = utcnow().date()
    aggregated_rows: dict[tuple[UUID, UUID, date], dict] = {}
    for _, row in df.iterrows():
        store_raw = str(row.get("store_code", "")).strip().upper()
        store_id = store_code_map.get(store_raw) or store_name_map.get(_canonical_store_name(store_raw))
        if store_id is None:
            continue

        sku_raw = str(row.get("sku_code", "")).strip().upper()
        sku_id = sku_code_map.get(sku_raw) or sku_style_map.get(sku_raw)
        if sku_id is None:
            continue

        week_value = row.get("week_start_date")
        parsed_week = pd.to_datetime(week_value, errors="coerce")
        week_start_date = parsed_week.date() if not pd.isna(parsed_week) else default_week_start

        key = (store_id, sku_id, week_start_date)
        if key not in aggregated_rows:
            aggregated_rows[key] = {
                "brand_id": brand_id,
                "upload_id": upload_id,
                "store_id": store_id,
                "sku_id": sku_id,
                "week_start_date": week_start_date,
                "units_sold": 0,
                "revenue": 0.0,
                "_has_revenue": False,
                "was_on_promotion": False,
                "was_in_stock": True,
            }

        record = aggregated_rows[key]
        record["units_sold"] += _safe_int(row.get("units_sold"), 0)

        revenue_raw = row.get("revenue")
        if revenue_raw is not None and not pd.isna(revenue_raw):
            try:
                record["revenue"] += float(revenue_raw)
                record["_has_revenue"] = True
            except (TypeError, ValueError):
                pass

        record["was_on_promotion"] = record["was_on_promotion"] or _normalise_bool(
            row.get("was_on_promotion"), False
        )
        record["was_in_stock"] = record["was_in_stock"] and _normalise_bool(
            row.get("was_in_stock"), True
        )

    rows: list[dict] = []
    for record in aggregated_rows.values():
        rows.append(
            {
                "brand_id": record["brand_id"],
                "upload_id": record["upload_id"],
                "store_id": record["store_id"],
                "sku_id": record["sku_id"],
                "week_start_date": record["week_start_date"],
                "units_sold": record["units_sold"],
                "revenue": record["revenue"] if record["_has_revenue"] else None,
                "was_on_promotion": record["was_on_promotion"],
                "was_in_stock": record["was_in_stock"],
            }
        )

    if not rows:
        return 0

    inserted = 0
    for batch in _chunked(rows):
        stmt = insert(SalesData).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_sales_brand_store_sku_week",
            set_={
                "units_sold": stmt.excluded.units_sold,
                "revenue": stmt.excluded.revenue,
                "was_on_promotion": stmt.excluded.was_on_promotion,
                "was_in_stock": stmt.excluded.was_in_stock,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
        inserted += len(batch)
    return inserted


async def _upsert_store_master(db: AsyncSession, brand_id: UUID, df: pd.DataFrame) -> int:
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "brand_id": brand_id,
                "store_code": str(row["store_code"]).upper(),
                "store_name": row["store_name"],
                "city": row.get("city"),
                "state": row.get("state"),
                "store_type": row.get("store_type"),
                "climate_zone": row.get("climate_zone"),
                "is_active": True if row.get("is_active") is None else bool(row.get("is_active")),
                "opening_date": row.get("opening_date"),
            }
        )

    if not rows:
        return 0

    inserted = 0
    for batch in _chunked(rows):
        stmt = insert(Store).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_stores_brand_store_code",
            set_={
                "store_name": stmt.excluded.store_name,
                "city": stmt.excluded.city,
                "state": stmt.excluded.state,
                "store_type": stmt.excluded.store_type,
                "climate_zone": stmt.excluded.climate_zone,
                "is_active": stmt.excluded.is_active,
                "opening_date": stmt.excluded.opening_date,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
        inserted += len(batch)
    return inserted


async def _upsert_sku_master(db: AsyncSession, brand_id: UUID, df: pd.DataFrame) -> int:
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "brand_id": brand_id,
                "sku_code": str(row["sku_code"]).upper(),
                "style_code": row["style_code"],
                "style_name": row["style_name"],
                "category": row["category"],
                "sub_category": row.get("sub_category"),
                "fabric": row.get("fabric"),
                "colour": row.get("colour"),
                "colour_family": row.get("colour_family"),
                "price_band": row.get("price_band"),
                "mrp": row.get("mrp"),
                "cost_price": row.get("cost_price"),
                "size": row.get("size"),
                "fit_type": row.get("fit_type"),
                "sku_type": row.get("sku_type") or "FASHION",
                "is_active": True if row.get("is_active") is None else bool(row.get("is_active")),
            }
        )

    if not rows:
        return 0

    inserted = 0
    for batch in _chunked(rows):
        stmt = insert(SKU).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_skus_brand_sku_code",
            set_={
                "style_code": stmt.excluded.style_code,
                "style_name": stmt.excluded.style_name,
                "category": stmt.excluded.category,
                "sub_category": stmt.excluded.sub_category,
                "fabric": stmt.excluded.fabric,
                "colour": stmt.excluded.colour,
                "colour_family": stmt.excluded.colour_family,
                "price_band": stmt.excluded.price_band,
                "mrp": stmt.excluded.mrp,
                "cost_price": stmt.excluded.cost_price,
                "size": stmt.excluded.size,
                "fit_type": stmt.excluded.fit_type,
                "sku_type": stmt.excluded.sku_type,
                "is_active": stmt.excluded.is_active,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
        inserted += len(batch)
    return inserted


async def _upsert_inventory(db: AsyncSession, brand_id: UUID, df: pd.DataFrame) -> int:
    _, sku_map = await _resolve_maps(db, brand_id, df)
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "brand_id": brand_id,
                "snapshot_date": row["snapshot_date"],
                "location_id": str(row["location_id"]),
                "location_type": row.get("location_type") or "STORE",
                "sku_id": sku_map[str(row["sku_code"]).upper()],
                "units_on_hand": int(row.get("units_on_hand") or 0),
                "units_in_transit": int(row.get("units_in_transit") or 0),
                "units_sold_7d": int(row.get("units_sold_7d") or 0),
                "units_sold_28d": int(row.get("units_sold_28d") or 0),
                "ros_7d": row.get("ros_7d"),
                "ros_28d": row.get("ros_28d"),
                "stock_cover_days": row.get("stock_cover_days"),
                "days_since_grn": row.get("days_since_grn"),
                "days_since_first_sale": row.get("days_since_first_sale"),
                "sell_through_pct": row.get("sell_through_pct"),
                "is_stockout": bool(row.get("is_stockout") or False),
                "is_new_arrival": bool(row.get("is_new_arrival") or False),
            }
        )

    if not rows:
        return 0

    inserted = 0
    for batch in _chunked(rows):
        stmt = insert(InventoryState).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_inventory_state_unique",
            set_={
                "units_on_hand": stmt.excluded.units_on_hand,
                "units_in_transit": stmt.excluded.units_in_transit,
                "units_sold_7d": stmt.excluded.units_sold_7d,
                "units_sold_28d": stmt.excluded.units_sold_28d,
                "ros_7d": stmt.excluded.ros_7d,
                "ros_28d": stmt.excluded.ros_28d,
                "stock_cover_days": stmt.excluded.stock_cover_days,
                "days_since_grn": stmt.excluded.days_since_grn,
                "days_since_first_sale": stmt.excluded.days_since_first_sale,
                "sell_through_pct": stmt.excluded.sell_through_pct,
                "is_stockout": stmt.excluded.is_stockout,
                "is_new_arrival": stmt.excluded.is_new_arrival,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
        inserted += len(batch)
    return inserted


async def _upsert_grn(db: AsyncSession, brand_id: UUID, user_id: UUID, df: pd.DataFrame) -> int:
    _, sku_map = await _resolve_maps(db, brand_id, df)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for _, row in df.iterrows():
        grouped[str(row["grn_code"])].append(row.to_dict())

    total_rows = 0
    for grn_code, lines in grouped.items():
        grn_date = lines[0]["grn_date"]
        result = await db.execute(select(GRN).where(and_(GRN.brand_id == brand_id, GRN.grn_code == grn_code)))
        grn = result.scalar_one_or_none()
        if grn is None:
            grn = GRN(
                brand_id=brand_id,
                grn_code=grn_code,
                grn_date=grn_date,
                warehouse_id=lines[0].get("warehouse_id"),
                supplier_name=lines[0].get("supplier_name"),
                status="RECEIVED",
                created_by=user_id,
            )
            db.add(grn)
            await db.flush()

        units_sum = 0
        for line in lines:
            sku_id = sku_map[str(line["sku_code"]).upper()]
            units = int(line["units_received"])
            units_sum += units
            stmt = insert(GRNLine).values(
                {
                    "grn_id": grn.id,
                    "brand_id": brand_id,
                    "sku_id": sku_id,
                    "units_received": units,
                }
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_grn_lines_grn_sku",
                set_={"units_received": stmt.excluded.units_received, "updated_at": utcnow()},
            )
            await db.execute(stmt)
            total_rows += 1

        grn.total_units = units_sum
        grn.total_skus = len(lines)

    return total_rows


async def _normalise_grade(raw_value: object, brand_id: UUID, db: AsyncSession) -> str | None:
    if raw_value is None or pd.isna(raw_value):
        return None
    raw = str(raw_value).strip()
    if raw == "":
        return None

    settings = await db.scalar(select(BrandSettings.config).where(BrandSettings.brand_id == brand_id))
    config = settings if isinstance(settings, dict) else {}
    grade_mapping = config.get("grade_mapping", {})
    if isinstance(grade_mapping, dict):
        if raw in grade_mapping:
            return str(grade_mapping[raw]).strip()
        raw_norm = raw.lower().strip()
        for key, value in grade_mapping.items():
            if str(key).lower().strip() == raw_norm:
                return str(value).strip()

    normalised = raw.strip()
    normalised = normalised.replace(" Stores", "").replace(" stores", "")
    normalised = normalised.replace("Grade ", "").replace("Tier ", "")
    if normalised in {"A+", "A", "B", "C"}:
        return normalised

    logger.warning("Cannot normalise grade: %s for brand %s", raw_value, brand_id)
    return None


def _normalise_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


def _safe_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if pd.isna(value):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


async def _upsert_store_grades(db: AsyncSession, brand_id: UUID, df: pd.DataFrame) -> int:
    store_name_map = await _resolve_store_name_map(db, brand_id)
    rows = []
    for _, row in df.iterrows():
        store_name = _canonical_store_name(row.get("store_name"))
        store_id = store_name_map.get(store_name)
        if store_id is None:
            continue
        grade = await _normalise_grade(row.get("grade"), brand_id, db)
        if grade is None:
            logger.warning(
                "Skipping store grade row: unable to normalise grade '%s' for store '%s'",
                row.get("grade"),
                store_name,
            )
            continue
        rows.append(
            {
                "brand_id": brand_id,
                "store_id": store_id,
                "product_category": str(row["product_category"]).strip(),
                "price_band": row.get("price_band"),
                "grade": grade,
            }
        )

    if not rows:
        return 0

    inserted = 0
    for batch in _chunked(rows):
        stmt = insert(StoreProductGrade).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_store_product_grades_unique",
            set_={
                "grade": stmt.excluded.grade,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
        inserted += len(batch)
    return inserted


async def _upsert_size_guide(db: AsyncSession, brand_id: UUID, df: pd.DataFrame) -> int:
    rows = []
    for _, row in df.iterrows():
        size = str(row.get("size", "")).strip()
        rows.append(
            {
                "brand_id": brand_id,
                "product_category": str(row.get("product_category", "")).strip(),
                "size": size,
                "size_type": str(row.get("size_type", "PIVOTAL")).strip().upper(),
                "min_max_ratio": _safe_int(row.get("min_max_ratio"), 0),
                "is_size_set": _normalise_bool(row.get("is_size_set"), size in {"S/M", "L/XL"}),
                "applies_to_grades": str(row.get("applies_to_grades", "ALL")).strip().upper() or "ALL",
                "display_order": _safe_int(row.get("display_order"), 0),
            }
        )

    if not rows:
        return 0

    inserted = 0
    for batch in _chunked(rows):
        stmt = insert(SizeGuide).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_size_guides_unique",
            set_={
                "size_type": stmt.excluded.size_type,
                "min_max_ratio": stmt.excluded.min_max_ratio,
                "is_size_set": stmt.excluded.is_size_set,
                "applies_to_grades": stmt.excluded.applies_to_grades,
                "display_order": stmt.excluded.display_order,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
        inserted += len(batch)
    return inserted


async def _upsert_reservation_types(db: AsyncSession, brand_id: UUID, df: pd.DataFrame) -> int:
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "brand_id": brand_id,
                "code": str(row["code"]).strip().upper(),
                "label": str(row.get("label", row["code"])).strip(),
                "deducts_from_first_allocation": _normalise_bool(
                    row.get("deducts_from_first_allocation"), True
                ),
                "display_order": _safe_int(row.get("display_order"), 0),
                "is_active": _normalise_bool(row.get("is_active"), True),
            }
        )

    if not rows:
        return 0

    inserted = 0
    for batch in _chunked(rows):
        stmt = insert(InventoryReservationType).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_inventory_reservation_types_brand_code",
            set_={
                "label": stmt.excluded.label,
                "deducts_from_first_allocation": stmt.excluded.deducts_from_first_allocation,
                "display_order": stmt.excluded.display_order,
                "is_active": stmt.excluded.is_active,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
        inserted += len(batch)
    return inserted


async def _upsert_buy_file(db: AsyncSession, upload: Upload, df: pd.DataFrame) -> int:
    brand_id = upload.brand_id
    raw_config = await db.scalar(select(BrandSettings.config).where(BrandSettings.brand_id == brand_id))
    config = raw_config if isinstance(raw_config, dict) else {}
    store_group_mapping = config.get("store_group_mapping", {})
    if not isinstance(store_group_mapping, dict):
        store_group_mapping = {}
    allocation_config = config.get("allocation", {})
    if not isinstance(allocation_config, dict):
        allocation_config = {}
    risk_group_mapping = allocation_config.get("risk_group_mapping", {})
    if not isinstance(risk_group_mapping, dict):
        risk_group_mapping = {}

    normalized_store_group_mapping = {str(key).strip().lower(): value for key, value in store_group_mapping.items()}
    normalized_risk_group_mapping = {str(key).strip().lower(): value for key, value in risk_group_mapping.items()}

    rows_by_sku: dict[str, dict] = {}
    for _, row in df.iterrows():
        base_style = _clean_str(row.get("sku_code"))
        size_value = _clean_str(row.get("size"))
        if not base_style:
            continue
        style_code = base_style.upper()
        sku_code = style_code if not size_value else f"{style_code}__{size_value.upper().replace(' ', '')}"
        store_group_rule = row.get("store_group_rule")
        style_risk_group = row.get("style_risk_group")
        resolved_min_grade = row.get("resolved_min_grade")
        if resolved_min_grade is None and store_group_rule is not None:
            resolved_min_grade = normalized_store_group_mapping.get(str(store_group_rule).strip().lower())

        resolved_risk_level = row.get("resolved_risk_level")
        if resolved_risk_level is None and style_risk_group is not None:
            resolved_risk_level = normalized_risk_group_mapping.get(str(style_risk_group).strip().lower())

        rows_by_sku[sku_code] = {
                "brand_id": brand_id,
                "sku_code": sku_code,
                "style_code": str(row.get("style_code") or style_code).strip().upper(),
                "style_name": str(row.get("style_name") or style_code).strip(),
                "category": str(row.get("category") or "Uncategorized").strip(),
                "fabric": row.get("fabric"),
                "colour": row.get("colour"),
                "colour_family": row.get("colour_family"),
                "price_band": row.get("price_band"),
                "mrp": row.get("mrp"),
                "size": row.get("size"),
                "store_group_rule": store_group_rule,
                "resolved_min_grade": resolved_min_grade,
                "style_risk_group": style_risk_group,
                "resolved_risk_level": resolved_risk_level,
                "story": row.get("story"),
                "sub_story": row.get("sub_story"),
                "buyer_name": row.get("buyer_name"),
                "vendor_name": row.get("vendor_name"),
                "is_active": True,
        }

    rows = list(rows_by_sku.values())
    for batch in _chunked(rows):
        stmt = insert(SKU).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_skus_brand_sku_code",
            set_={
                "style_code": stmt.excluded.style_code,
                "style_name": stmt.excluded.style_name,
                "category": stmt.excluded.category,
                "fabric": stmt.excluded.fabric,
                "colour": stmt.excluded.colour,
                "colour_family": stmt.excluded.colour_family,
                "price_band": stmt.excluded.price_band,
                "mrp": stmt.excluded.mrp,
                "size": stmt.excluded.size,
                "store_group_rule": stmt.excluded.store_group_rule,
                "resolved_min_grade": stmt.excluded.resolved_min_grade,
                "style_risk_group": stmt.excluded.style_risk_group,
                "resolved_risk_level": stmt.excluded.resolved_risk_level,
                "story": stmt.excluded.story,
                "sub_story": stmt.excluded.sub_story,
                "buyer_name": stmt.excluded.buyer_name,
                "vendor_name": stmt.excluded.vendor_name,
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)

    plan_name = upload.filename
    if "buy_plan_name" in df.columns and not df.empty:
        raw_name = df["buy_plan_name"].iloc[0]
        if raw_name is not None and not pd.isna(raw_name) and str(raw_name).strip():
            plan_name = str(raw_name).strip()
    buy_plan_file = await db.scalar(
        select(BuyPlanFile).where(BuyPlanFile.brand_id == brand_id, BuyPlanFile.name == plan_name)
    )
    if buy_plan_file is None:
        buy_plan_file = BuyPlanFile(
            brand_id=brand_id,
            upload_id=upload.id,
            season_id=None,
            name=plan_name,
            source_filename=upload.filename,
            created_by=upload.uploaded_by,
        )
        db.add(buy_plan_file)
        await db.flush()

    season = await db.scalar(
        select(Season)
        .where(
            Season.brand_id == brand_id,
            Season.status == SeasonStatus.ACTIVE,
        )
        .order_by(Season.start_date.desc())
    )
    if season is None:
        season = Season(
            brand_id=brand_id,
            name="SS26",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 9, 30),
            status=SeasonStatus.ACTIVE,
        )
        db.add(season)
        await db.flush()

    buy_plan_file.season_id = season.id

    sku_rows = await db.execute(select(SKU).where(SKU.brand_id == brand_id))
    sku_map = {sku.sku_code.upper(): sku.id for sku in sku_rows.scalars().all()}

    plan_line_map: dict[tuple[UUID, str | None], dict] = {}
    reservation_by_key: dict[tuple[UUID, str | None], dict[str, int]] = {}
    has_ecom = "ecom_reserved_qty" in df.columns
    has_ars = "ars_reserved_qty" in df.columns
    for _, row in df.iterrows():
        base_style = _clean_str(row.get("sku_code"))
        size_value = _clean_str(row.get("size"))
        if not base_style:
            continue
        style_code = base_style.upper()
        sku_code = style_code if not size_value else f"{style_code}__{size_value.upper().replace(' ', '')}"
        sku_id = sku_map.get(sku_code)
        if sku_id is None:
            continue
        store_group = row.get("store_group_rule")
        key = (sku_id, store_group)
        if key not in reservation_by_key:
            reservation_by_key[key] = {"ecom": 0, "ars": 0}
        if has_ecom:
            reservation_by_key[key]["ecom"] += _safe_int(row.get("ecom_reserved_qty"), 0)
        if has_ars:
            reservation_by_key[key]["ars"] += _safe_int(row.get("ars_reserved_qty"), 0)
        if key not in plan_line_map:
            plan_line_map[key] = {
                "buy_plan_file_id": buy_plan_file.id,
                "brand_id": brand_id,
                "sku_id": sku_id,
                "store_group_rule": store_group,
                "style_risk_group": row.get("style_risk_group"),
                "total_buy_qty": _safe_int(row.get("total_buy_qty"), 0),
                "expected_first_allocation_qty": _safe_int(
                    row.get("expected_first_allocation_qty"), 0
                ),
            }
        else:
            plan_line_map[key]["total_buy_qty"] += _safe_int(row.get("total_buy_qty"), 0)
            plan_line_map[key]["expected_first_allocation_qty"] += _safe_int(
                row.get("expected_first_allocation_qty"), 0
            )

    plan_line_rows = list(plan_line_map.values())
    if plan_line_rows:
        for batch in _chunked(plan_line_rows):
            stmt = insert(BuyPlanLine).values(batch)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_buy_plan_lines_file_sku_group",
                set_={
                    "style_risk_group": stmt.excluded.style_risk_group,
                    "total_buy_qty": stmt.excluded.total_buy_qty,
                    "expected_first_allocation_qty": stmt.excluded.expected_first_allocation_qty,
                    "updated_at": utcnow(),
                },
            )
            await db.execute(stmt)

    buy_plan_lines = (
        await db.execute(
            select(BuyPlanLine).where(
                BuyPlanLine.buy_plan_file_id == buy_plan_file.id,
                BuyPlanLine.brand_id == brand_id,
            )
        )
    ).scalars().all()

    existing_grn = await db.scalar(
        select(GRN).where(GRN.brand_id == brand_id, GRN.grn_code == "SS26-INITIAL-STOCK")
    )
    if existing_grn is not None:
        existing_lines = (
            await db.execute(select(GRNLine).where(GRNLine.grn_id == existing_grn.id))
        ).scalars().all()
        if existing_lines:
            line_ids = [line.id for line in existing_lines]
            await db.execute(
                GRNLineReservation.__table__.delete().where(GRNLineReservation.grn_line_id.in_(line_ids))
            )
            await db.execute(GRNLine.__table__.delete().where(GRNLine.id.in_(line_ids)))
        await db.delete(existing_grn)
        await db.flush()

    total_units = 0
    unique_skus = {line.sku_id for line in buy_plan_lines}
    for line in buy_plan_lines:
        reserved = reservation_by_key.get((line.sku_id, line.store_group_rule), {"ecom": 0, "ars": 0})
        units_received = int(line.total_buy_qty or 0)
        available = units_received - reserved.get("ecom", 0) - reserved.get("ars", 0)
        if available <= 0:
            available = units_received
        total_units += available

    grn = GRN(
        brand_id=brand_id,
        grn_code="SS26-INITIAL-STOCK",
        grn_date=date.today(),
        supplier_name="Buy Plan Import",
        status="RECEIVED",
        total_units=total_units,
        total_skus=len(unique_skus),
        season_id=buy_plan_file.season_id,
    )
    db.add(grn)
    await db.flush()

    reservation_types = (
        await db.execute(
            select(InventoryReservationType).where(InventoryReservationType.brand_id == brand_id)
        )
    ).scalars().all()

    grn_lines: list[GRNLine] = []
    for line in buy_plan_lines:
        reserved = reservation_by_key.get((line.sku_id, line.store_group_rule), {"ecom": 0, "ars": 0})
        grn_line = GRNLine(
            grn_id=grn.id,
            brand_id=brand_id,
            sku_id=line.sku_id,
            units_received=int(line.total_buy_qty or 0),
            total_buy_qty=int(line.total_buy_qty or 0),
            ecom_reserved_qty=int(reserved.get("ecom", 0)),
            ars_reserved_qty=int(reserved.get("ars", 0)),
            buy_plan_line_id=line.id,
        )
        db.add(grn_line)
        grn_lines.append(grn_line)

    await db.flush()

    if reservation_types:
        for grn_line in grn_lines:
            for reservation_type in reservation_types:
                reserved_qty = 0
                if reservation_type.code.upper() == "ECOM":
                    reserved_qty = int(grn_line.ecom_reserved_qty or 0)
                elif reservation_type.code.upper() == "ARS":
                    reserved_qty = int(grn_line.ars_reserved_qty or 0)
                db.add(
                    GRNLineReservation(
                        grn_line_id=grn_line.id,
                        brand_id=brand_id,
                        reservation_type_id=reservation_type.id,
                        reserved_qty=reserved_qty,
                    )
                )

    await seed_warehouse_inventory(grn.id, brand_id, db)

    return len(rows)


async def process_upload(db: AsyncSession, upload: Upload) -> Upload:
    validator = UploadValidator()
    upload.status = UploadStatus.PROCESSING
    upload.processing_started_at = utcnow()
    await db.flush()

    content = read_upload_file(upload.s3_key)
    raw_df = dataframe_from_bytes(content)
    normalized_df = normalize(raw_df, upload.upload_type.value)

    schema_errors = validator.validate_schema(normalized_df, upload.upload_type.value)
    if any(err.row == 0 for err in schema_errors):
        upload.status = UploadStatus.FAILED
        upload.error_summary = {"errors": [e.__dict__ for e in schema_errors]}
        upload.failed_rows = len(normalized_df)
        upload.total_rows = len(normalized_df)
        upload.processing_completed_at = utcnow()
        return upload

    await _bootstrap_dimensions_for_upload(db, upload, normalized_df)

    reference_errors = await validator.validate_references(
        normalized_df, upload.upload_type.value, upload.brand_id, db
    )
    business_errors = validator.validate_business_rules(normalized_df, upload.upload_type.value)

    all_errors = schema_errors + reference_errors + business_errors
    error_rows = _error_row_set(all_errors)

    valid_rows = []
    for idx, row in normalized_df.iterrows():
        row_num = idx + 2
        if row_num not in error_rows:
            valid_rows.append(row)
    valid_df = pd.DataFrame(valid_rows, columns=normalized_df.columns)

    successes = 0
    if upload.upload_type.value == "SALES":
        successes = await _upsert_sales(db, upload.brand_id, upload.id, valid_df)
    elif upload.upload_type.value == "STORE_MASTER":
        successes = await _upsert_store_master(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "SKU_MASTER":
        successes = await _upsert_sku_master(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "INVENTORY":
        successes = await _upsert_inventory(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "GRN":
        successes = await _upsert_grn(db, upload.brand_id, upload.uploaded_by, valid_df)
    elif upload.upload_type.value == "STORE_GRADES":
        successes = await _upsert_store_grades(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "SIZE_GUIDE":
        successes = await _upsert_size_guide(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "RESERVATION_TYPES":
        successes = await _upsert_reservation_types(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "BUY_FILE":
        successes = await _upsert_buy_file(db, upload, valid_df)

    failures = len(error_rows)
    upload.total_rows = len(normalized_df)
    upload.successful_rows = successes
    upload.failed_rows = failures

    if failures == 0:
        upload.status = UploadStatus.COMPLETED
    elif successes > 0:
        upload.status = UploadStatus.PARTIAL
    else:
        upload.status = UploadStatus.FAILED

    if upload.status in {UploadStatus.COMPLETED, UploadStatus.PARTIAL} and successes > 0:
        await _ensure_simple_mode_season(db, upload.brand_id, upload, valid_df)
        if upload.upload_type.value in {"SALES", "INVENTORY", "GRN"}:
            await _run_simple_mode_jobs(db, upload.brand_id)

    error_report_path: str | None = None
    if all_errors:
        error_df = _errors_to_df(all_errors)
        error_report_path = str(ERROR_DIR / f"upload-errors-{upload.id}.csv")
        error_df.to_csv(error_report_path, index=False)

    upload.error_summary = {
        "row_errors": [e.__dict__ for e in all_errors],
        "error_report_path": error_report_path,
    }
    upload.processing_completed_at = utcnow()
    return upload
