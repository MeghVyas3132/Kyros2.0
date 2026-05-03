from __future__ import annotations

# Ingestion flow map:
# 1) Upload task marks file PROCESSING and loads bytes from storage.
# 2) File is normalized/validated, then lookups (stores/SKUs) are preloaded once.
# 3) Records are converted to dicts and bulk-upserted in batches with retry + commit cadence.
# 4) Progress is emitted per phase (parsing, dimensions, sales/buy/size/grades, complete/error).
# 5) Upload row is finalized with counters and optional post-ingestion jobs.

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
import hashlib
import os
from pathlib import Path
import re
from typing import Awaitable, Callable, Iterable
from uuid import UUID

logger = logging.getLogger(__name__)

import pandas as pd
import redis.asyncio as redis
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AllocationSession,
    AllocationStatus,
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
from app.services.allocation.store_profile import build_all_store_profiles
from app.config import get_settings
from app.services.ingestion.bulk import execute_with_batching
from app.services.ingestion.lookup import build_lookup_maps, normalize_key
from app.services.ingestion.normalizer import normalize
from app.services.ingestion.validator import RowError, UploadValidator
from app.services.inventory.snapshot import seed_warehouse_inventory
from app.utils.csv_parser import dataframe_from_bytes
from app.utils.date_utils import utcnow
from app.utils.s3 import read_upload_file

settings = get_settings()
ERROR_DIR = Path(settings.local_storage_path) / "errors"
ERROR_DIR.mkdir(parents=True, exist_ok=True)
UPSERT_BATCH_SIZE = 1000
SYNTHETIC_SALES_WEEKS = 8


class IngestionRowError(ValueError):
    def __init__(self, row_index: int, field: str, message: str) -> None:
        self.row_index = row_index
        self.field = field
        super().__init__(f"Row {row_index} [{field}]: {message}")

ProgressReporter = Callable[[str, int, int, str], Awaitable[None]]


def _build_progress_reporter(task_id: str | None, upload_id: str) -> ProgressReporter:
    redis_url = os.getenv("REDIS_URL") or settings.redis_url
    redis_client: redis.Redis | None = None
    if redis_url:
        try:
            redis_client = redis.from_url(redis_url, decode_responses=True)
        except Exception:
            redis_client = None

    progress_task_id = task_id or upload_id
    key = f"ingestion_progress:{progress_task_id}"

    async def _report(stage: str, processed: int, total: int, message: str) -> None:
        if redis_client is None:
            return

        status = "PROCESSING"
        if stage == "complete":
            status = "COMPLETED"
        elif stage == "error":
            status = "FAILED"

        payload = {
            "task_id": progress_task_id,
            "upload_id": upload_id,
            "stage": stage,
            "processed": processed,
            "total": total,
            "message": message,
            "status": status,
        }

        try:
            await redis_client.setex(key, 3600, json.dumps(payload))
        except Exception:
            logger.debug("Skipping progress update for task %s", progress_task_id)

    return _report


def _require_columns(df: pd.DataFrame, required: list[str], sheet_name: str) -> None:
    missing = [column for column in required if column not in df.columns]
    if not missing:
        return
    raise ValueError(
        f"Column(s) {missing} not found in sheet '{sheet_name}'. Found columns: {list(df.columns)}"
    )


async def _resolve_ingestion_season(db: AsyncSession, brand_id: UUID) -> Season:
    """Pick the season ingestion writes against.

    Prefers any in-flight pre-season status (PLANNING / BUYING / RECEIVING /
    ALLOCATING / IN_SEASON), then falls back to DRAFT, then to whatever exists.
    If the brand has zero seasons (e.g. a brand-new pilot dropped their
    workbook before creating a season), we auto-create a default 6-month
    PLANNING season so the smart-upload flow works out of the box. The
    planner can rename it later from ``Setup → Seasons``.

    The historical name ``ACTIVE`` is no longer in the enum (see migration
    0009_season_status_expanded) — the substitute set captures every status
    where new buy/sales data can land legitimately.
    """
    preferred = (
        SeasonStatus.PLANNING,
        SeasonStatus.BUYING,
        SeasonStatus.RECEIVING,
        SeasonStatus.ALLOCATING,
        SeasonStatus.IN_SEASON,
    )
    season = await db.scalar(
        select(Season)
        .where(Season.brand_id == brand_id, Season.status.in_(preferred))
        .order_by(Season.start_date.desc())
        .limit(1)
    )
    if season is not None:
        return season

    season = await db.scalar(
        select(Season)
        .where(Season.brand_id == brand_id, Season.status == SeasonStatus.DRAFT)
        .order_by(Season.start_date.desc())
        .limit(1)
    )
    if season is not None:
        return season

    season = await db.scalar(
        select(Season).where(Season.brand_id == brand_id).order_by(Season.start_date.desc()).limit(1)
    )
    if season is not None:
        return season

    # Deliberate: do NOT auto-create. Season setup is the first explicit step
    # in the planner workflow — autocreating here would hide a missing
    # onboarding step and confuse the user later when they wonder where the
    # season came from. The frontend post-login redirect routes a brand-new
    # tenant to /setup/seasons; only programmatic clients (no UI) should
    # ever reach this branch, and they get a clear, actionable error.
    raise ValueError(
        "No season found for this brand. Create a season at "
        "Setup → Seasons before uploading the buy file."
    )


async def _load_grade_mapping(db: AsyncSession, brand_id: UUID) -> dict[str, str]:
    settings_row = await db.scalar(select(BrandSettings.config).where(BrandSettings.brand_id == brand_id))
    config = settings_row if isinstance(settings_row, dict) else {}
    grade_mapping = config.get("grade_mapping", {})
    if not isinstance(grade_mapping, dict):
        return {}
    return {str(key).strip().lower(): str(value).strip() for key, value in grade_mapping.items()}


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


async def _upsert_sales(
    db: AsyncSession,
    brand_id: UUID,
    upload_id: UUID,
    df: pd.DataFrame,
    progress: ProgressReporter,
) -> tuple[int, dict[str, int]]:
    _require_columns(df, ["store_code", "sku_code", "units_sold"], "SS25 SALES HISTORY")

    # Fix 1.4: Removed the destructive `DELETE FROM sales_data WHERE brand_id = ...`
    # that wiped all historical data before re-upload. The upsert (on_conflict_do_update)
    # below at _statement_factory already handles updates correctly via the
    # uq_sales_brand_store_sku_week unique constraint.

    store_map, store_name_map, sku_map = await build_lookup_maps(db, brand_id)
    aggregated_rows: dict[tuple[UUID, UUID, date], dict] = {}

    skipped_store_rows = 0
    skipped_sku_rows = 0
    zero_qty_rows = 0
    skipped_missing_date = 0
    synthetic_weeking_rows = 0
    used_synthetic_weeking = False
    synthetic_week_starts: list[date] | None = None

    await progress("sales", 0, len(df), "Preparing sales records...")
    for idx, row in enumerate(df.to_dict(orient="records"), start=1):
        store_raw = normalize_key(row.get("store_code"))
        store_id = store_map.get(store_raw) or store_name_map.get(store_raw)
        if store_id is None:
            skipped_store_rows += 1
            continue

        sku_raw = normalize_key(row.get("sku_code"))
        sku_id = sku_map.get(sku_raw)
        if sku_id is None:
            skipped_sku_rows += 1
            continue

        units_sold = _safe_int(row.get("units_sold"), 0)
        if units_sold <= 0:
            zero_qty_rows += 1
            continue

        revenue_raw = row.get("revenue")
        parsed_revenue: float | None = None
        if revenue_raw is not None and not pd.isna(revenue_raw):
            try:
                parsed_revenue = float(revenue_raw)
            except (TypeError, ValueError):
                pass

        was_on_promotion = _normalise_bool(row.get("was_on_promotion"), False)
        was_in_stock = _normalise_bool(row.get("was_in_stock"), None)

        parsed_week = _try_parse_week_start_date(row.get("week_start_date"))
        if parsed_week is None:
            if synthetic_week_starts is None:
                synthetic_week_starts = _generate_synthetic_week_starts(SYNTHETIC_SALES_WEEKS)
            targets = _spread_units_across_weeks(units_sold, synthetic_week_starts)
            synthetic_weeking_rows += 1
            used_synthetic_weeking = True
        else:
            targets = {parsed_week: units_sold}

        for week_start_date, split_units in targets.items():
            if split_units <= 0:
                continue

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
            record["units_sold"] += split_units

            if parsed_revenue is not None and units_sold > 0:
                revenue_share = parsed_revenue * (split_units / units_sold)
                record["revenue"] += revenue_share
                record["_has_revenue"] = True

            record["was_on_promotion"] = record["was_on_promotion"] or was_on_promotion
            if was_in_stock is not None:
                record["was_in_stock"] = (
                    record["was_in_stock"] and was_in_stock
                )
            # if None, leave existing value unchanged

        if idx % 10000 == 0:
            await progress("sales", idx, len(df), f"Preparing sales records: {idx:,}/{len(df):,}")

    logger.info("Skipped %d rows: missing week_start_date", skipped_missing_date)

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

    distinct_weeks = len({row["week_start_date"] for row in rows})
    if rows and distinct_weeks < 4 and not used_synthetic_weeking:
        raise ValueError(
            "Sales data appears to have collapsed into fewer than 4 weeks. "
            "Please verify week_start_date mapping and re-upload the sales file."
        )

    if not rows:
        return 0, {
            "skipped_store_rows": skipped_store_rows,
            "skipped_sku_rows": skipped_sku_rows,
            "zero_qty_rows": zero_qty_rows,
            "failed_batches_rows": 0,
            "synthetic_weeking_rows": synthetic_weeking_rows,
            "skipped_missing_date": skipped_missing_date,
        }

    async def _sales_progress(done: int, total: int) -> None:
        if done % 10000 == 0 or done == total:
            await progress("sales", done, total, f"Importing sales history: {done:,} of {total:,} rows")

    def _statement_factory(batch: list[dict]) -> object:
        stmt = insert(SalesData).values(batch)
        return stmt.on_conflict_do_update(
            constraint="uq_sales_brand_store_sku_week",
            set_={
                "upload_id": stmt.excluded.upload_id,
                "units_sold": stmt.excluded.units_sold,
                "revenue": stmt.excluded.revenue,
                "was_on_promotion": stmt.excluded.was_on_promotion,
                "was_in_stock": stmt.excluded.was_in_stock,
                "updated_at": utcnow(),
            },
        )

    inserted, failed_rows = await execute_with_batching(
        db=db,
        records=rows,
        statement_factory=_statement_factory,
        progress_callback=_sales_progress,
        label="sales_upsert",
    )

    return inserted, {
        "skipped_store_rows": skipped_store_rows,
        "skipped_sku_rows": skipped_sku_rows,
        "zero_qty_rows": zero_qty_rows,
        "failed_batches_rows": failed_rows,
        "synthetic_weeking_rows": synthetic_weeking_rows,
        "skipped_missing_date": skipped_missing_date,
    }


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


async def _upsert_grn(
    db: AsyncSession,
    brand_id: UUID,
    user_id: UUID,
    df: pd.DataFrame,
    progress: ProgressReporter | None = None,
) -> int:
    _require_columns(df, ["grn_code", "grn_date", "sku_code", "units_received"], "GRN")

    _, _, sku_map = await build_lookup_maps(db, brand_id)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in df.to_dict(orient="records"):
        grouped[normalize_key(row.get("grn_code"))].append(row)

    if progress is not None:
        await progress("grn", 0, len(df), "Preparing GRN records...")

    grn_codes = [code for code in grouped.keys() if code]
    existing_grns = (
        await db.execute(
            select(GRN).where(GRN.brand_id == brand_id, GRN.grn_code.in_(grn_codes))
        )
    ).scalars().all()
    grn_by_code = {normalize_key(grn.grn_code): grn for grn in existing_grns}

    season = await _resolve_ingestion_season(db, brand_id)

    grn_rows: list[dict] = []
    for grn_code, lines in grouped.items():
        if not grn_code:
            continue
        first = lines[0]
        grn_rows.append(
            {
                "brand_id": brand_id,
                "grn_code": grn_code,
                "grn_date": first.get("grn_date"),
                "warehouse_id": first.get("warehouse_id"),
                "supplier_name": first.get("supplier_name"),
                "season_id": season.id,
                "status": "RECEIVED",
                "created_by": user_id,
            }
        )

    if grn_rows:
        def _grn_stmt(batch: list[dict]) -> object:
            stmt = insert(GRN).values(batch)
            return stmt.on_conflict_do_update(
                constraint="uq_grns_brand_grn_code",
                set_={
                    "grn_date": stmt.excluded.grn_date,
                    "warehouse_id": stmt.excluded.warehouse_id,
                    "supplier_name": stmt.excluded.supplier_name,
                    "season_id": stmt.excluded.season_id,
                    "status": stmt.excluded.status,
                    "updated_at": utcnow(),
                },
            )

        await execute_with_batching(
            db=db,
            records=grn_rows,
            statement_factory=_grn_stmt,
            label="grn_upsert",
        )

    refreshed_grns = (
        await db.execute(
            select(GRN).where(GRN.brand_id == brand_id, GRN.grn_code.in_(grn_codes))
        )
    ).scalars().all()
    grn_by_code = {normalize_key(grn.grn_code): grn for grn in refreshed_grns}

    grn_line_rows: list[dict] = []
    total_processed = 0
    for grn_code, lines in grouped.items():
        grn = grn_by_code.get(grn_code)
        if grn is None:
            continue

        units_sum = 0
        sku_ids_seen: set[UUID] = set()
        for line in lines:
            sku_id = sku_map.get(normalize_key(line.get("sku_code")))
            if sku_id is None:
                continue
            units = _safe_int(line.get("units_received"), 0)
            units_sum += units
            sku_ids_seen.add(sku_id)
            grn_line_rows.append(
                {
                    "grn_id": grn.id,
                    "brand_id": brand_id,
                    "sku_id": sku_id,
                    "units_received": units,
                }
            )
            total_processed += 1

        grn.total_units = units_sum
        grn.total_skus = len(sku_ids_seen)

    if grn_line_rows:
        async def _grn_lines_progress(done: int, total: int) -> None:
            if progress is not None:
                await progress("grn", done, total, f"Importing GRN lines: {done:,}/{total:,}")

        def _grn_line_stmt(batch: list[dict]) -> object:
            stmt = insert(GRNLine).values(batch)
            return stmt.on_conflict_do_update(
                constraint="uq_grn_lines_grn_sku",
                set_={"units_received": stmt.excluded.units_received, "updated_at": utcnow()},
            )

        await execute_with_batching(
            db=db,
            records=grn_line_rows,
            statement_factory=_grn_line_stmt,
            progress_callback=_grn_lines_progress,
            label="grn_line_upsert",
        )

    return total_processed


def _normalise_grade(raw_value: object, grade_mapping: dict[str, str]) -> str | None:
    if raw_value is None or pd.isna(raw_value):
        return None
    raw = str(raw_value).strip()
    if raw == "":
        return None

    if raw.lower().strip() in grade_mapping:
        return grade_mapping[raw.lower().strip()]

    normalised = raw.strip()
    normalised = normalised.replace(" Stores", "").replace(" stores", "")
    normalised = normalised.replace("Grade ", "").replace("Tier ", "")
    if normalised in {"A+", "A", "B", "C"}:
        return normalised

    logger.warning("Cannot normalise grade: %s", raw_value)
    return None


def _normalise_bool(value: object, default: bool | None = False) -> bool | None:
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


def _try_parse_week_start_date(raw_value: object) -> date | None:
    if raw_value is None or str(raw_value).strip() == "":
        return None

    text = str(raw_value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return parsed.date()

    return None


def _generate_synthetic_week_starts(week_count: int) -> list[date]:
    count = max(week_count, 4)
    today = utcnow().date()
    anchor = today - timedelta(days=today.weekday())
    starts = [anchor - timedelta(days=7 * offset) for offset in range(count - 1, -1, -1)]
    return starts


def _spread_units_across_weeks(units_sold: int, week_starts: list[date]) -> dict[date, int]:
    if units_sold <= 0 or not week_starts:
        return {}

    allocation = {week: 0 for week in week_starts}
    base = units_sold // len(week_starts)
    remainder = units_sold % len(week_starts)

    for week in week_starts:
        allocation[week] = base

    for idx in range(remainder):
        allocation[week_starts[idx]] += 1

    non_zero = {week: qty for week, qty in allocation.items() if qty > 0}
    if non_zero:
        return non_zero

    return {week_starts[0]: units_sold}


async def _upsert_store_grades(
    db: AsyncSession,
    brand_id: UUID,
    df: pd.DataFrame,
    progress: ProgressReporter,
) -> tuple[int, int]:
    _require_columns(df, ["store_name", "product_category", "grade"], "Store_Grading")

    store_name_map = await _resolve_store_name_map(db, brand_id)
    grade_mapping = await _load_grade_mapping(db, brand_id)
    rows = []
    skipped_store_rows = 0
    for _, row in df.iterrows():
        store_name = _canonical_store_name(row.get("store_name"))
        store_id = store_name_map.get(store_name)
        if store_id is None:
            skipped_store_rows += 1
            continue
        grade = _normalise_grade(row.get("grade"), grade_mapping)
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
        return 0, skipped_store_rows

    async def _grades_progress(done: int, total: int) -> None:
        await progress("stores", done, total, f"Importing store grades: {done:,}/{total:,}")

    def _statement_factory(batch: list[dict]) -> object:
        stmt = insert(StoreProductGrade).values(batch)
        return stmt.on_conflict_do_update(
            constraint="uq_store_product_grades_unique",
            set_={
                "grade": stmt.excluded.grade,
                "updated_at": utcnow(),
            },
        )

    inserted, _ = await execute_with_batching(
        db=db,
        records=rows,
        statement_factory=_statement_factory,
        progress_callback=_grades_progress,
        label="store_grade_upsert",
    )
    return inserted, skipped_store_rows


async def _upsert_size_guide(
    db: AsyncSession,
    brand_id: UUID,
    df: pd.DataFrame,
    progress: ProgressReporter,
) -> int:
    _require_columns(df, ["product_category", "size", "min_max_ratio"], "SIZE GUIDE")
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

    async def _size_progress(done: int, total: int) -> None:
        await progress("size_guide", done, total, f"Importing size guide: {done:,}/{total:,}")

    def _statement_factory(batch: list[dict]) -> object:
        stmt = insert(SizeGuide).values(batch)
        return stmt.on_conflict_do_update(
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

    inserted, _ = await execute_with_batching(
        db=db,
        records=rows,
        statement_factory=_statement_factory,
        progress_callback=_size_progress,
        label="size_guide_upsert",
    )
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


async def _upsert_buy_file(
    db: AsyncSession,
    upload: Upload,
    df: pd.DataFrame,
    progress: ProgressReporter,
) -> int:
    _require_columns(df, ["sku_code"], "BUY FILE")
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
    await progress("skus", 0, len(df), "Preparing SKU records from buy file...")
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

    async def _sku_progress(done: int, total: int) -> None:
        await progress("skus", done, total, f"Ensuring SKUs: {done:,}/{total:,}")

    def _sku_stmt(batch: list[dict]) -> object:
        stmt = insert(SKU).values(batch)
        return stmt.on_conflict_do_update(
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

    await execute_with_batching(
        db=db,
        records=rows,
        statement_factory=_sku_stmt,
        progress_callback=_sku_progress,
        label="buy_sku_upsert",
    )

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

    season = await _resolve_ingestion_season(db, brand_id)

    buy_plan_file.season_id = season.id

    _, _, sku_map = await build_lookup_maps(db, brand_id)

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
        async def _buy_progress(done: int, total: int) -> None:
            await progress("buy_file", done, total, f"Importing buy lines: {done:,}/{total:,}")

        def _buy_stmt(batch: list[dict]) -> object:
            stmt = insert(BuyPlanLine).values(batch)
            return stmt.on_conflict_do_update(
                constraint="uq_buy_plan_lines_file_sku_group",
                set_={
                    "style_risk_group": stmt.excluded.style_risk_group,
                    "total_buy_qty": stmt.excluded.total_buy_qty,
                    "expected_first_allocation_qty": stmt.excluded.expected_first_allocation_qty,
                    "updated_at": utcnow(),
                },
            )

        await execute_with_batching(
            db=db,
            records=plan_line_rows,
            statement_factory=_buy_stmt,
            progress_callback=_buy_progress,
            label="buy_plan_line_upsert",
        )

    buy_plan_lines = (
        await db.execute(
            select(BuyPlanLine).where(
                BuyPlanLine.buy_plan_file_id == buy_plan_file.id,
                BuyPlanLine.brand_id == brand_id,
            )
        )
    ).scalars().all()

    grn_code = f"{season.name}-INITIAL-STOCK"
    existing_grn = await db.scalar(
        select(GRN).where(GRN.brand_id == brand_id, GRN.grn_code == grn_code)
    )
    if existing_grn is not None:
        locked_sessions = await db.scalar(
            select(func.count(AllocationSession.id)).where(
                AllocationSession.grn_id == existing_grn.id,
                AllocationSession.status.not_in([AllocationStatus.FAILED, AllocationStatus.DRAFT]),
            )
        )
        if (locked_sessions or 0) > 0:
            raise ValueError(
                "Cannot replace GRN with active or approved allocations. Archive the current allocations first."
            )

    total_units = 0
    unique_skus = {line.sku_id for line in buy_plan_lines}
    for line in buy_plan_lines:
        reserved = reservation_by_key.get((line.sku_id, line.store_group_rule), {"ecom": 0, "ars": 0})
        units_received = int(line.total_buy_qty or 0)
        available = units_received - reserved.get("ecom", 0) - reserved.get("ars", 0)
        if available <= 0:
            available = units_received
        total_units += available

    if existing_grn is None:
        grn = GRN(
            brand_id=brand_id,
            grn_code=grn_code,
            grn_date=date.today(),
            supplier_name="Buy Plan Import",
            status="RECEIVED",
            total_units=total_units,
            total_skus=len(unique_skus),
            season_id=buy_plan_file.season_id,
        )
        db.add(grn)
        await db.flush()
    else:
        grn = existing_grn
        grn.grn_date = date.today()
        grn.supplier_name = "Buy Plan Import"
        grn.status = "RECEIVED"
        grn.total_units = total_units
        grn.total_skus = len(unique_skus)
        grn.season_id = buy_plan_file.season_id
        await db.flush()

    reservation_types = (
        await db.execute(
            select(InventoryReservationType).where(InventoryReservationType.brand_id == brand_id)
        )
    ).scalars().all()

    aggregated_by_sku: dict[UUID, dict[str, int | UUID | None]] = {}
    for line in buy_plan_lines:
        reserved = reservation_by_key.get((line.sku_id, line.store_group_rule), {"ecom": 0, "ars": 0})
        row = aggregated_by_sku.setdefault(
            line.sku_id,
            {
                "grn_id": grn.id,
                "brand_id": brand_id,
                "sku_id": line.sku_id,
                "units_received": 0,
                "total_buy_qty": 0,
                "ecom_reserved_qty": 0,
                "ars_reserved_qty": 0,
                "buy_plan_line_id": line.id,
            },
        )
        row["units_received"] = int(row["units_received"] or 0) + int(line.total_buy_qty or 0)
        row["total_buy_qty"] = int(row["total_buy_qty"] or 0) + int(line.total_buy_qty or 0)
        row["ecom_reserved_qty"] = int(row["ecom_reserved_qty"] or 0) + int(reserved.get("ecom", 0))
        row["ars_reserved_qty"] = int(row["ars_reserved_qty"] or 0) + int(reserved.get("ars", 0))

    grn_line_rows = list(aggregated_by_sku.values())

    if grn_line_rows:
        def _grn_line_stmt(batch: list[dict]) -> object:
            stmt = insert(GRNLine).values(batch)
            return stmt.on_conflict_do_update(
                constraint="uq_grn_lines_grn_sku",
                set_={
                    "units_received": stmt.excluded.units_received,
                    "total_buy_qty": stmt.excluded.total_buy_qty,
                    "ecom_reserved_qty": stmt.excluded.ecom_reserved_qty,
                    "ars_reserved_qty": stmt.excluded.ars_reserved_qty,
                    "buy_plan_line_id": stmt.excluded.buy_plan_line_id,
                    "updated_at": utcnow(),
                },
            )

        await execute_with_batching(
            db=db,
            records=grn_line_rows,
            statement_factory=_grn_line_stmt,
            label="grn_line_upsert",
        )

    keep_sku_ids = [row["sku_id"] for row in grn_line_rows]
    existing_lines = (
        await db.execute(select(GRNLine).where(GRNLine.grn_id == grn.id))
    ).scalars().all()
    stale_lines = [line for line in existing_lines if line.sku_id not in keep_sku_ids]
    if stale_lines:
        stale_line_ids = [line.id for line in stale_lines]
        await db.execute(
            GRNLineReservation.__table__.delete().where(GRNLineReservation.grn_line_id.in_(stale_line_ids))
        )
        await db.execute(GRNLine.__table__.delete().where(GRNLine.id.in_(stale_line_ids)))

    if reservation_types:
        fresh_grn_lines = (
            await db.execute(select(GRNLine).where(GRNLine.grn_id == grn.id, GRNLine.brand_id == brand_id))
        ).scalars().all()
        reservation_rows: list[dict] = []
        for grn_line in fresh_grn_lines:
            for reservation_type in reservation_types:
                reserved_qty = 0
                if reservation_type.code.upper() == "ECOM":
                    reserved_qty = int(grn_line.ecom_reserved_qty or 0)
                elif reservation_type.code.upper() == "ARS":
                    reserved_qty = int(grn_line.ars_reserved_qty or 0)
                reservation_rows.append(
                    {
                        "grn_line_id": grn_line.id,
                        "brand_id": brand_id,
                        "reservation_type_id": reservation_type.id,
                        "reserved_qty": reserved_qty,
                    }
                )

        if reservation_rows:
            def _reservation_stmt(batch: list[dict]) -> object:
                stmt = insert(GRNLineReservation).values(batch)
                return stmt.on_conflict_do_update(
                    constraint="uq_grn_line_reservations_unique",
                    set_={
                        "reserved_qty": stmt.excluded.reserved_qty,
                        "updated_at": utcnow(),
                    },
                )

            await execute_with_batching(
                db=db,
                records=reservation_rows,
                statement_factory=_reservation_stmt,
                label="grn_line_reservation_upsert",
            )

    await seed_warehouse_inventory(grn.id, brand_id, db)

    return len(rows)


async def process_upload(db: AsyncSession, upload: Upload, task_id: str | None = None) -> Upload:
    validator = UploadValidator()
    progress = _build_progress_reporter(task_id=task_id, upload_id=str(upload.id))

    await progress("init", 0, 1, "Preparing upload processing...")
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
        await progress(
            "error",
            upload.failed_rows,
            upload.total_rows,
            "Upload failed due to schema errors",
        )
        return upload

    await progress("bootstrap", 0, 1, "Bootstrapping master data...")
    await _bootstrap_dimensions_for_upload(db, upload, normalized_df)

    reference_errors = await validator.validate_references(
        normalized_df, upload.upload_type.value, upload.brand_id, db
    )
    business_errors = validator.validate_business_rules(normalized_df, upload.upload_type.value)

    all_errors = schema_errors + reference_errors + business_errors
    error_rows = _error_row_set(all_errors)

    await progress("validate", 0, len(normalized_df), "Validating rows...")
    valid_rows = []
    for idx, row in normalized_df.iterrows():
        row_num = idx + 2
        if row_num not in error_rows:
            valid_rows.append(row)
        if (idx + 1) % 10000 == 0:
            await progress("validate", idx + 1, len(normalized_df), f"Validating rows: {idx + 1:,}/{len(normalized_df):,}")
    valid_df = pd.DataFrame(valid_rows, columns=normalized_df.columns)

    successes = 0
    if upload.upload_type.value == "SALES":
        successes, _ = await _upsert_sales(db, upload.brand_id, upload.id, valid_df, progress)
    elif upload.upload_type.value == "STORE_MASTER":
        successes = await _upsert_store_master(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "SKU_MASTER":
        successes = await _upsert_sku_master(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "INVENTORY":
        successes = await _upsert_inventory(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "GRN":
        successes = await _upsert_grn(db, upload.brand_id, upload.uploaded_by, valid_df, progress)
    elif upload.upload_type.value == "STORE_GRADES":
        successes, _ = await _upsert_store_grades(db, upload.brand_id, valid_df, progress)
    elif upload.upload_type.value == "SIZE_GUIDE":
        successes = await _upsert_size_guide(db, upload.brand_id, valid_df, progress)
    elif upload.upload_type.value == "RESERVATION_TYPES":
        successes = await _upsert_reservation_types(db, upload.brand_id, valid_df)
    elif upload.upload_type.value == "BUY_FILE":
        successes = await _upsert_buy_file(db, upload, valid_df, progress)

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
        if upload.upload_type.value == "SALES":
            try:
                season = await _resolve_ingestion_season(db, upload.brand_id)
                await build_all_store_profiles(db, upload.brand_id, season.id)
                logger.info(
                    "Store profiles built for brand=%s season=%s",
                    upload.brand_id,
                    season.name,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Store profile build failed (non-blocking): %s", exc)

            # Refresh the category × price-band bridge so cold-start GRNs
            # uploaded later can resolve real demand for new SKU codes. This
            # is a no-op if SKU master is empty.
            try:
                from app.services.allocation.category_bridge import rebuild_bridge_for_brand

                rows = await rebuild_bridge_for_brand(db, upload.brand_id)
                logger.info(
                    "Category bridge rebuilt for brand=%s rows=%d",
                    upload.brand_id,
                    rows,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Category bridge rebuild failed (non-blocking): %s", exc)
        elif upload.upload_type.value == "BUY_FILE":
            # The buy file introduces brand-new SKUs whose (category, price_band)
            # didn't exist before — rebuild so they can match against existing sales.
            try:
                from app.services.allocation.category_bridge import rebuild_bridge_for_brand

                rows = await rebuild_bridge_for_brand(db, upload.brand_id)
                logger.info(
                    "Category bridge rebuilt for brand=%s after buy file upload rows=%d",
                    upload.brand_id,
                    rows,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Category bridge rebuild failed (non-blocking): %s", exc)

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
    await progress("complete", upload.total_rows or 0, upload.total_rows or 0, f"Upload {upload.status.value.lower()}")
    return upload
