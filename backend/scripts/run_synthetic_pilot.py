"""Synthetic-pilot orchestrator.

Loads the two synthetic Excel files at the repo root into a fresh tenant,
exercises the full ingestion + allocation pipeline, and emits KPIs to
``VERDICT.md`` for sign-off.

The script is meant to be run from a developer box with the dev Postgres
already up (`docker compose up -d postgres redis`). Idempotent — it wipes
the synthetic-pilot brand each run so KPIs reflect the latest engine.

Usage:
    cd backend
    DATABASE_URL=postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev \\
    REDIS_URL=redis://localhost:6379/0 \\
    JWT_SECRET_KEY=dev-secret-key-change-in-production-minimum-32-chars \\
    APP_ENV=test \\
        python -m scripts.run_synthetic_pilot
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import delete as delete_stmt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]
SS26_FILE = ROOT / "SS26 Master File For Allocation V12.xlsx"
GRADING_FILE = ROOT / "Store Grading.xlsx"
VERDICT_OUT = ROOT / "VERDICT.md"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import (  # noqa: E402
    AllocationLine,
    AllocationSession,
    AllocationStatus,
    Brand,
    BrandSettings,
    BuyPlanFile,
    BuyPlanLine,
    Cluster,
    GRN,
    GRNLine,
    InventoryReservationType,
    InventoryState,
    SalesData,
    Season,
    SeasonOTB,
    SeasonStatus,
    SizeGuide,
    SKU,
    Store,
    StoreDisplayCapacity,
    StoreProductGrade,
    Upload,
    UploadStatus,
    UploadType,
    User,
    UserRole,
)
from app.services.allocation.engine import AllocationEngine  # noqa: E402
from app.services.allocation.store_profile import build_all_store_profiles  # noqa: E402
from app.services.ingestion.processor import (  # noqa: E402
    _bootstrap_stores_from_names,
    _upsert_buy_file,
    _upsert_sales,
    _upsert_size_guide,
    _upsert_store_grades,
)
from app.services.inventory.snapshot import build_snapshot_for_brand  # noqa: E402
from app.utils.security import get_password_hash  # noqa: E402

PILOT_BRAND_SLUG = "synthetic-pilot"
PILOT_BRAND_NAME = "Synthetic Pilot Brand"
PILOT_USER_EMAIL = "pilot@synthetic.kyros.local"

DEFAULT_CAPACITY_BY_GRADE = {"A+": 80, "A": 60, "B": 40, "C": 25}
SEASON_START = date(2026, 4, 1)
SEASON_END = date(2026, 9, 30)


async def _noop_progress(stage: str, processed: int, total: int, message: str) -> None:
    return None


def _log(msg: str) -> None:
    print(f"[pilot] {msg}", flush=True)


# ─── Tenant lifecycle ────────────────────────────────────────────────────────


async def _wipe_brand(session_factory: async_sessionmaker) -> None:
    async with session_factory() as db:
        brand = (
            await db.execute(select(Brand).where(Brand.slug == PILOT_BRAND_SLUG))
        ).scalars().first()
        if brand is None:
            return

        bid = brand.id
        for table in (
            AllocationLine,
            AllocationSession,
            GRNLine,
            GRN,
            BuyPlanLine,
            BuyPlanFile,
            SalesData,
            InventoryState,
            StoreProductGrade,
            SizeGuide,
            SeasonOTB,
            Season,
            SKU,
            StoreDisplayCapacity,
            Store,
            Cluster,
            InventoryReservationType,
            Upload,
            BrandSettings,
            User,
        ):
            await db.execute(delete_stmt(table).where(table.brand_id == bid))
        await db.execute(delete_stmt(Brand).where(Brand.id == bid))
        await db.commit()


async def _create_brand_and_user(session_factory: async_sessionmaker) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as db:
        brand = Brand(name=PILOT_BRAND_NAME, slug=PILOT_BRAND_SLUG, is_active=True)
        db.add(brand)
        await db.flush()
        db.add(BrandSettings(brand_id=brand.id, config={}))

        user = User(
            brand_id=brand.id,
            email=PILOT_USER_EMAIL,
            hashed_password=get_password_hash("pilot-pilot-pilot"),
            full_name="Pilot Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        season = Season(
            brand_id=brand.id,
            name="SS26",
            start_date=SEASON_START,
            end_date=SEASON_END,
            status=SeasonStatus.PLANNING,
        )
        db.add(season)
        await db.commit()
        return brand.id, user.id


# ─── Excel → DataFrame mappers ───────────────────────────────────────────────


def _read_excel_sheets() -> dict[str, pd.DataFrame]:
    if not SS26_FILE.exists() or not GRADING_FILE.exists():
        raise FileNotFoundError(
            f"Synthetic data not found. Expected: {SS26_FILE}, {GRADING_FILE}"
        )
    _log(f"Reading {SS26_FILE.name}...")
    ss26 = pd.read_excel(SS26_FILE, sheet_name=None)
    _log(f"Reading {GRADING_FILE.name}...")
    grading = pd.read_excel(GRADING_FILE, sheet_name=None)

    return {
        "buy": ss26["SS26 BUY FILE"],
        "sales": ss26["SS25 SALES HISTORY"],
        "size_guide": ss26["SIZE GUIDE"],
        "grades": grading["Sheet1"],
    }


def _map_grades_df(df: pd.DataFrame) -> pd.DataFrame:
    """Map Store Grading.xlsx → STORE_GRADES upload schema."""
    out = pd.DataFrame(
        {
            "store_name": df["Store Name"].astype(str).str.strip(),
            "product_category": df["Product"].astype(str).str.strip(),
            "price_band": df["Price Band"].astype(str).str.strip(),
            "grade": df["Store Grade - Prod Price Band"].astype(str).str.strip(),
        }
    )
    return out


def _map_size_guide_df(df: pd.DataFrame) -> pd.DataFrame:
    """SIZE GUIDE sheet → SIZE_GUIDE upload schema."""
    out = pd.DataFrame(
        {
            "product_category": df["STORE NAME"].astype(str).str.strip(),
            "size": df["SIZE"].astype(str).str.strip(),
            "min_max_ratio": pd.to_numeric(df["MIN / MAX"], errors="coerce").fillna(0).astype(int),
            "size_type": df["SIZE TYPE"].astype(str).str.strip(),
        }
    )
    return out[out["size"].astype(str).str.len() > 0]


def _map_buy_df(df: pd.DataFrame) -> pd.DataFrame:
    """SS26 BUY FILE → BUY_FILE upload schema."""
    keep = df[df["STYLE NUMBER"].notna()].copy()
    out = pd.DataFrame(
        {
            "buyer_name": keep["BUYER NAME"],
            "vendor_name": keep["VENDOR"],
            "sku_code": keep["STYLE NUMBER"].astype(str).str.strip(),
            "style_code": keep["STYLE NUMBER"].astype(str).str.strip(),
            "style_name": keep["PRODUCT"].astype(str).str.strip(),
            "category": keep["PRODUCT"].astype(str).str.strip(),
            "fabric": keep["TOP FABRIC"],
            "colour": keep["Standardized Colour"],
            "colour_family": keep["Colour Family"],
            "price_band": keep["MRP"].apply(_mrp_to_priceband),
            "mrp": pd.to_numeric(keep["MRP"], errors="coerce"),
            "size": keep["SIZE"].astype(str).str.strip(),
            "store_group_rule": keep["Store Group"],
            "style_risk_group": keep["Style Group"],
            "story": keep["STORY"],
            "sub_story": keep["SUB STORY"],
            "total_buy_qty": pd.to_numeric(keep["Total Buy Qty"], errors="coerce").fillna(0).astype(int),
            "ecom_reserved_qty": pd.to_numeric(keep["ECOM Reserved Qty"], errors="coerce").fillna(0).astype(int),
            "ars_reserved_qty": pd.to_numeric(keep["Reserved Qty For ARS"], errors="coerce").fillna(0).astype(int),
            "expected_first_allocation_qty": pd.to_numeric(
                keep["Total Available For Replenishment"], errors="coerce"
            ).fillna(0).astype(int),
            "buy_plan_name": "SS26 Master Buy",
        }
    )
    out = out[out["size"].astype(str).str.len() > 0]
    return out


def _map_sales_df(df: pd.DataFrame, sample_rows: int | None = None) -> pd.DataFrame:
    """SS25 SALES HISTORY → SALES upload schema (no week_start_date — engine
    spreads via synthetic week starts)."""
    keep = df[df["STORE NAME"].notna() & df["STYLE_NUMBER"].notna()].copy()
    if sample_rows is not None and len(keep) > sample_rows:
        keep = keep.sample(n=sample_rows, random_state=42).reset_index(drop=True)
    out = pd.DataFrame(
        {
            "store_code": keep["STORE NAME"].astype(str).str.strip(),
            "sku_code": keep["STYLE_NUMBER"].astype(str).str.strip(),
            "units_sold": pd.to_numeric(keep["SALES QTY"], errors="coerce").fillna(0).astype(int),
            "revenue": pd.to_numeric(keep["NET SALES"], errors="coerce"),
            "category": keep["DEPARTMENT"],
            "DEPARTMENT": keep["DEPARTMENT"],
            "MRP": pd.to_numeric(keep["MRP"], errors="coerce"),
            "PRICEBAND": keep["PRICEBAND"],
            "SIZE_FINAL": keep["SIZE_FINAL"],
            "Standardized Colour": keep["Standardized Colour"],
            "MATERIAL": keep["MATERIAL"],
            "size": keep["SIZE_FINAL"].astype(str).str.strip(),
        }
    )
    out = out[out["units_sold"] >= 0]
    return out


def _mrp_to_priceband(value: object) -> str | None:
    try:
        mrp = float(value)
    except (TypeError, ValueError):
        return None
    if mrp <= 0:
        return None
    bands = [
        (1000, "a.0 - 1000"),
        (2000, "b.1001 - 2000"),
        (3000, "c.2001 - 3000"),
        (4000, "d.3001 - 4000"),
        (5000, "e.4001 - 5000"),
        (7000, "f.5001 - 7000"),
        (10000, "g.7001 - 10000"),
        (13000, "h.10000 - 13000"),
        (15000, "i.13000 - 15000"),
    ]
    for upper, label in bands:
        if mrp <= upper:
            return label
    return "z.Above - 15000"


# ─── Pipeline stages ─────────────────────────────────────────────────────────


async def _ingest_grades(
    session_factory: async_sessionmaker, brand_id: uuid.UUID, df: pd.DataFrame
) -> dict[str, int]:
    async with session_factory() as db:
        # Bootstrap stores from grading file (so SS25 sales can match by name).
        await _bootstrap_stores_from_names(db, brand_id, df["store_name"].dropna().tolist())
        await db.commit()

    async with session_factory() as db:
        rows, _ = await _upsert_store_grades(db, brand_id, df, _noop_progress)
        await db.commit()

    async with session_factory() as db:
        store_count = await db.scalar(select(func.count(Store.id)).where(Store.brand_id == brand_id))
        grade_count = await db.scalar(
            select(func.count(StoreProductGrade.id)).where(StoreProductGrade.brand_id == brand_id)
        )
    return {"grade_rows_upserted": int(rows), "stores": int(store_count or 0), "grade_records": int(grade_count or 0)}


async def _ingest_size_guide(
    session_factory: async_sessionmaker, brand_id: uuid.UUID, df: pd.DataFrame
) -> dict[str, int]:
    async with session_factory() as db:
        rows = await _upsert_size_guide(db, brand_id, df, _noop_progress)
        await db.commit()
        size_count = await db.scalar(
            select(func.count(SizeGuide.id)).where(SizeGuide.brand_id == brand_id)
        )
    return {"size_rows_upserted": int(rows), "size_guide_records": int(size_count or 0)}


async def _ingest_buy_file(
    session_factory: async_sessionmaker,
    brand_id: uuid.UUID,
    user_id: uuid.UUID,
    df: pd.DataFrame,
) -> dict[str, int]:
    async with session_factory() as db:
        upload = Upload(
            brand_id=brand_id,
            uploaded_by=user_id,
            upload_type=UploadType.BUY_FILE,
            filename="SS26 Master File For Allocation V12.xlsx",
            s3_key="synthetic/buy.xlsx",
            status=UploadStatus.PROCESSING,
        )
        db.add(upload)
        await db.flush()
        rows = await _upsert_buy_file(db, upload, df, _noop_progress)
        upload.status = UploadStatus.COMPLETED
        await db.commit()

    async with session_factory() as db:
        sku_count = await db.scalar(select(func.count(SKU.id)).where(SKU.brand_id == brand_id))
        plan_count = await db.scalar(
            select(func.count(BuyPlanLine.id)).where(BuyPlanLine.brand_id == brand_id)
        )
    return {"buy_lines_upserted": int(rows), "sku_count": int(sku_count or 0), "buy_plan_lines": int(plan_count or 0)}


async def _ingest_sales(
    session_factory: async_sessionmaker,
    brand_id: uuid.UUID,
    user_id: uuid.UUID,
    df: pd.DataFrame,
) -> dict[str, int]:
    async with session_factory() as db:
        from app.services.ingestion.processor import _bootstrap_sales_dimensions

        upload = Upload(
            brand_id=brand_id,
            uploaded_by=user_id,
            upload_type=UploadType.SALES,
            filename="SS25_sales.xlsx",
            s3_key="synthetic/sales.xlsx",
            status=UploadStatus.PROCESSING,
        )
        db.add(upload)
        await db.flush()
        await _bootstrap_sales_dimensions(db, brand_id, df)
        await db.commit()

    async with session_factory() as db:
        upload = (
            await db.execute(
                select(Upload)
                .where(Upload.brand_id == brand_id, Upload.upload_type == UploadType.SALES)
                .order_by(Upload.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        sales_rows, summary = await _upsert_sales(db, brand_id, upload.id, df, _noop_progress)
        upload.status = UploadStatus.COMPLETED
        await db.commit()

    async with session_factory() as db:
        weeks = await db.scalar(
            select(func.count(func.distinct(SalesData.week_start_date))).where(SalesData.brand_id == brand_id)
        )
        units = await db.scalar(
            select(func.coalesce(func.sum(SalesData.units_sold), 0)).where(SalesData.brand_id == brand_id)
        )
        rows = await db.scalar(
            select(func.count(SalesData.id)).where(SalesData.brand_id == brand_id)
        )
    return {
        "sales_rows_upserted": int(sales_rows),
        "distinct_weeks": int(weeks or 0),
        "total_units": int(units or 0),
        "sales_records": int(rows or 0),
        **{k: int(v) for k, v in summary.items()},
    }


async def _seed_display_capacity(session_factory: async_sessionmaker, brand_id: uuid.UUID) -> int:
    """Heuristic: use the most-common grade for each (store, category) to set
    a max_styles ceiling. This exercises Phase 4's planogram-aware constraint."""
    async with session_factory() as db:
        # Most common grade per store (used as the store's "tier")
        rows = (
            await db.execute(
                select(
                    StoreProductGrade.store_id,
                    StoreProductGrade.product_category,
                    StoreProductGrade.grade,
                ).where(StoreProductGrade.brand_id == brand_id)
            )
        ).all()
        if not rows:
            return 0

        # Pick the most-common grade per store as a coarse store tier.
        store_grade_counts: dict[uuid.UUID, Counter] = defaultdict(Counter)
        for store_id, category, grade in rows:
            store_grade_counts[store_id][_normalize_grade(grade)] += 1
        store_tier: dict[uuid.UUID, str] = {
            store_id: counter.most_common(1)[0][0] for store_id, counter in store_grade_counts.items()
        }

        seen: set[tuple[uuid.UUID, str]] = set()
        capacity_rows: list[dict[str, Any]] = []
        for store_id, category, _grade in rows:
            cat = (category or "").strip()
            if not cat:
                continue
            key = (store_id, cat.lower())
            if key in seen:
                continue
            seen.add(key)
            tier = store_tier.get(store_id, "C")
            max_styles = DEFAULT_CAPACITY_BY_GRADE.get(tier, 25)
            capacity_rows.append(
                {
                    "brand_id": brand_id,
                    "store_id": store_id,
                    "category": cat,
                    "max_styles": max_styles,
                    "max_units": max_styles * 6,
                }
            )

        # Wipe any prior capacity rows to keep the run idempotent
        await db.execute(
            delete_stmt(StoreDisplayCapacity).where(StoreDisplayCapacity.brand_id == brand_id)
        )
        await db.flush()
        if capacity_rows:
            db.add_all([StoreDisplayCapacity(**row) for row in capacity_rows])
        await db.commit()
        return len(capacity_rows)


def _normalize_grade(value: str | None) -> str:
    if not value:
        return "C"
    s = str(value).strip().upper()
    if "A+" in s:
        return "A+"
    if s.startswith("A"):
        return "A"
    if s.startswith("B"):
        return "B"
    if s.startswith("C"):
        return "C"
    return "C"


async def _create_synthetic_grn(
    session_factory: async_sessionmaker,
    brand_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    top_n_styles: int = 25,
) -> tuple[uuid.UUID, dict[str, int]]:
    """Build a GRN from the most-bought SS26 styles. Includes all sizes for
    each style. Returns (grn_id, stats)."""
    async with session_factory() as db:
        season = (
            await db.execute(
                select(Season).where(Season.brand_id == brand_id).order_by(Season.start_date.desc())
            )
        ).scalars().first()

        # Top styles by total_buy_qty (sum across sizes)
        top_rows = (
            await db.execute(
                select(SKU.style_code, func.sum(BuyPlanLine.total_buy_qty).label("qty"))
                .join(BuyPlanLine, BuyPlanLine.sku_id == SKU.id)
                .where(SKU.brand_id == brand_id, BuyPlanLine.brand_id == brand_id)
                .group_by(SKU.style_code)
                .order_by(func.sum(BuyPlanLine.total_buy_qty).desc())
                .limit(top_n_styles * 5)
            )
        ).all()
        top_styles = [r[0] for r in top_rows if (r[1] or 0) > 0][:top_n_styles]

        if not top_styles:
            raise RuntimeError("No buy-plan SKUs with positive qty — synthetic GRN cannot be built.")

        skus = (
            await db.execute(
                select(SKU).where(SKU.brand_id == brand_id, SKU.style_code.in_(top_styles))
            )
        ).scalars().all()

        # 80% of total_buy_qty becomes "received" — leaves room for follow-up GRNs.
        plan_qty_map = {
            (line.sku_id): line.total_buy_qty
            for line in (
                await db.execute(
                    select(BuyPlanLine).where(
                        BuyPlanLine.brand_id == brand_id, BuyPlanLine.sku_id.in_([s.id for s in skus])
                    )
                )
            ).scalars().all()
        }

        grn = GRN(
            brand_id=brand_id,
            grn_code=f"SYN-GRN-{uuid.uuid4().hex[:6].upper()}",
            grn_date=date(2026, 4, 5),
            status="RECEIVED",
            total_units=0,
            total_skus=0,
            season_id=season.id if season else None,
            created_by=user_id,
            supplier_name="Synthetic Vendor",
        )
        db.add(grn)
        await db.flush()

        total_units = 0
        total_skus = 0
        for sku in skus:
            buy_qty = int(plan_qty_map.get(sku.id) or 0)
            received = max(int(buy_qty * 0.8), 6) if buy_qty > 0 else 6
            db.add(
                GRNLine(
                    grn_id=grn.id,
                    brand_id=brand_id,
                    sku_id=sku.id,
                    units_received=received,
                    total_buy_qty=buy_qty or received,
                )
            )
            total_units += received
            total_skus += 1

        grn.total_units = total_units
        grn.total_skus = total_skus
        await db.commit()
        return grn.id, {"styles": len(top_styles), "skus": total_skus, "units": total_units}


async def _run_allocation(
    session_factory: async_sessionmaker, brand_id: uuid.UUID, grn_id: uuid.UUID
) -> tuple[uuid.UUID, float]:
    engine = AllocationEngine()
    started = time.perf_counter()
    async with session_factory() as db:
        session = await engine.generate(grn_id, brand_id, db)
        await db.commit()
        sid = session.id
    elapsed = time.perf_counter() - started
    return sid, elapsed


async def _measure_kpis(
    session_factory: async_sessionmaker,
    brand_id: uuid.UUID,
    grn_id: uuid.UUID,
    session_id: uuid.UUID,
) -> dict[str, Any]:
    async with session_factory() as db:
        lines = (
            await db.execute(
                select(AllocationLine).where(AllocationLine.session_id == session_id)
            )
        ).scalars().all()
        grn = await db.get(GRN, grn_id)
        capacity_rows = (
            await db.execute(
                select(
                    StoreDisplayCapacity.store_id,
                    StoreDisplayCapacity.category,
                    StoreDisplayCapacity.max_styles,
                    StoreDisplayCapacity.max_units,
                ).where(StoreDisplayCapacity.brand_id == brand_id)
            )
        ).all()
        sku_rows = (
            await db.execute(
                select(SKU.id, SKU.category).where(
                    SKU.brand_id == brand_id,
                    SKU.id.in_({line.sku_id for line in lines}),
                )
            )
        ).all()
        category_by_sku = {sku_id: cat for sku_id, cat in sku_rows}

    if not lines:
        return {"lines": 0}

    # Pull style_code per sku for cap checks (planogram counts styles, not sku rows).
    async with session_factory() as db:
        style_rows = (
            await db.execute(
                select(SKU.id, SKU.style_code).where(
                    SKU.brand_id == brand_id,
                    SKU.id.in_({line.sku_id for line in lines}),
                )
            )
        ).all()
    style_by_sku = {sku_id: style_code for sku_id, style_code in style_rows}

    qtys = [int(line.ai_recommended_qty or 0) for line in lines]
    positive_lines = [line for line in lines if (line.ai_recommended_qty or 0) > 0]
    distinct_stores = len({line.store_id for line in positive_lines})
    distinct_skus = len({line.sku_id for line in positive_lines})
    distinct_styles = len({style_by_sku.get(line.sku_id) for line in positive_lines})

    units_received = int(grn.total_units or 0) if grn else sum(qtys)
    units_allocated = sum(int(line.ai_recommended_qty or 0) for line in lines)

    # Concentration: top-10% stores' share of allocated units.
    units_per_store: dict[uuid.UUID, int] = defaultdict(int)
    for line in positive_lines:
        units_per_store[line.store_id] += int(line.ai_recommended_qty or 0)
    sorted_units = sorted(units_per_store.values(), reverse=True)
    top10_count = max(1, len(sorted_units) // 10)
    top10_share = (sum(sorted_units[:top10_count]) / max(sum(sorted_units), 1)) * 100

    # Capacity violation: per (store, category), units must not exceed max_units,
    # and distinct *styles* must not exceed max_styles.
    capacity_idx = {
        (store_id, (cat or "").strip().lower()): (int(max_styles or 0), int(max_units or 0))
        for store_id, cat, max_styles, max_units in capacity_rows
    }
    units_by_store_cat: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
    styles_by_store_cat: dict[tuple[uuid.UUID, str], set] = defaultdict(set)
    for line in positive_lines:
        cat = (category_by_sku.get(line.sku_id) or "").strip().lower()
        key = (line.store_id, cat)
        units_by_store_cat[key] += int(line.ai_recommended_qty or 0)
        styles_by_store_cat[key].add(style_by_sku.get(line.sku_id))

    cap_violations_units = 0
    cap_violations_styles = 0
    for key, units in units_by_store_cat.items():
        cap = capacity_idx.get(key)
        if cap is None:
            continue
        max_styles, max_units = cap
        if max_units > 0 and units > max_units:
            cap_violations_units += 1
        if max_styles > 0 and len(styles_by_store_cat[key]) > max_styles:
            cap_violations_styles += 1

    # Reasoning coverage: % of positive lines with at least one non-empty narrative chunk.
    narratives = 0
    confidence_counter: Counter = Counter()
    tier_counter: Counter = Counter()
    for line in positive_lines:
        reasoning = line.ai_reasoning or {}
        narrative_pieces = [
            reasoning.get("narrative"),
            reasoning.get("ai_reasoning_human"),
            reasoning.get("narrative_demand"),
            reasoning.get("narrative_cap"),
            reasoning.get("narrative_adjustments"),
        ]
        if any((piece or "").strip() for piece in narrative_pieces):
            narratives += 1
        confidence = reasoning.get("confidence_tier") or line.ai_confidence
        if confidence:
            confidence_counter[str(confidence)] += 1
        ros_source = reasoning.get("ros_source")
        if ros_source:
            tier_counter[str(ros_source)] += 1

    reasoning_coverage = (narratives / max(len(positive_lines), 1)) * 100

    # Weeks-of-cover: prefer the engine's `weeks_cover_at_recommended` field.
    cover_values: list[float] = []
    for line in positive_lines:
        reasoning = line.ai_reasoning or {}
        wc = (
            reasoning.get("weeks_cover_at_recommended")
            or reasoning.get("weeks_cover")
            or reasoning.get("weeks_of_cover")
        )
        if wc is None:
            continue
        try:
            cover_values.append(float(wc))
        except (TypeError, ValueError):
            continue

    return {
        "lines_total": len(lines),
        "lines_with_positive_qty": len(positive_lines),
        "distinct_stores_with_alloc": distinct_stores,
        "distinct_skus_with_alloc": distinct_skus,
        "distinct_styles_with_alloc": distinct_styles,
        "units_received": units_received,
        "units_allocated": units_allocated,
        "alloc_received_ratio": round((units_allocated / max(units_received, 1)) * 100, 1),
        "top10_pct_store_share": round(top10_share, 1),
        "capacity_violations_units": cap_violations_units,
        "capacity_violations_styles": cap_violations_styles,
        "reasoning_coverage_pct": round(reasoning_coverage, 1),
        "confidence_distribution": dict(confidence_counter),
        "demand_tier_distribution": dict(tier_counter),
        "weeks_cover_p50": round(statistics.median(cover_values), 1) if cover_values else None,
        "weeks_cover_p90": round(_percentile(cover_values, 90), 1) if cover_values else None,
    }


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ─── Main ────────────────────────────────────────────────────────────────────


async def _async_main() -> None:
    db_url = os.environ.get("DATABASE_URL") or "postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev"
    engine = create_async_engine(db_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    overall_start = time.perf_counter()
    summary: dict[str, Any] = {"started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "stages": {}}

    try:
        _log("Wiping any prior synthetic-pilot brand...")
        await _wipe_brand(session_factory)

        _log("Creating fresh tenant + season...")
        brand_id, user_id = await _create_brand_and_user(session_factory)
        summary["brand_id"] = str(brand_id)

        _log("Reading Excel files...")
        sheets = _read_excel_sheets()

        _log("Ingest: store grades (also bootstraps stores)...")
        grades_df = _map_grades_df(sheets["grades"])
        summary["stages"]["grades"] = await _ingest_grades(session_factory, brand_id, grades_df)

        _log("Ingest: size guide...")
        sg_df = _map_size_guide_df(sheets["size_guide"])
        summary["stages"]["size_guide"] = await _ingest_size_guide(session_factory, brand_id, sg_df)

        _log("Ingest: SS26 buy file (creates SKUs + buy plan)...")
        buy_df = _map_buy_df(sheets["buy"])
        summary["stages"]["buy"] = await _ingest_buy_file(session_factory, brand_id, user_id, buy_df)

        _log("Ingest: SS25 sales history (subsample)...")
        sales_df = _map_sales_df(sheets["sales"], sample_rows=80_000)
        summary["stages"]["sales"] = await _ingest_sales(session_factory, brand_id, user_id, sales_df)

        _log("Seed display-capacity rows from grades...")
        cap_count = await _seed_display_capacity(session_factory, brand_id)
        summary["stages"]["capacity"] = {"rows": cap_count}

        _log("Build inventory snapshot for store profiles...")
        async with session_factory() as db:
            built = await build_snapshot_for_brand(brand_id, date(2026, 4, 1), db)
            await db.commit()
        summary["stages"]["snapshot"] = {"rows": int(built or 0)}

        _log("Build store profiles from sales...")
        async with session_factory() as db:
            season = (
                await db.execute(
                    select(Season).where(Season.brand_id == brand_id).order_by(Season.start_date.desc())
                )
            ).scalars().first()
            try:
                profile_count = await build_all_store_profiles(db, brand_id, season.id)
                await db.commit()
            except Exception as exc:  # noqa: BLE001
                _log(f"  store-profile build failed (non-fatal): {exc}")
                profile_count = 0
        summary["stages"]["store_profiles"] = {"profiles": int(profile_count or 0)}

        _log("Build synthetic GRN from top-25 SS26 styles...")
        grn_id, grn_stats = await _create_synthetic_grn(session_factory, brand_id, user_id, top_n_styles=25)
        summary["stages"]["grn"] = grn_stats

        _log("Run allocation engine...")
        session_id, runtime = await _run_allocation(session_factory, brand_id, grn_id)
        summary["stages"]["allocation"] = {"session_id": str(session_id), "runtime_seconds": round(runtime, 2)}

        _log("Measure KPIs...")
        kpis = await _measure_kpis(session_factory, brand_id, grn_id, session_id)
        summary["kpis"] = kpis

    finally:
        await engine.dispose()

    summary["total_runtime_seconds"] = round(time.perf_counter() - overall_start, 2)
    out_path = Path(__file__).resolve().parent / "synthetic_pilot_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    _log(f"Wrote {out_path}")
    _log(f"Total runtime: {summary['total_runtime_seconds']}s")
    print(json.dumps(summary, indent=2, default=str))


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
