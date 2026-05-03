import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from io import BytesIO

import pandas as pd
import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import (
    GRN,
    GRNLine,
    SalesData,
    Season,
    SizeGuide,
    SKU,
    Store,
    StoreCategoryDemand,
    StoreProductGrade,
    Upload,
    UploadType,
    User,
    UserRole,
)
from app.routers._helpers import envelope
from app.services.ingestion.mapping import (
    UPLOAD_FIELD_ALIASES,
    apply_column_mapping,
    available_fields,
    resolve_column_mapping,
    MappingRequiredError,
)
from app.services.ingestion.understanding import (
    DATA_UNDERSTANDING_MIN_CONFIDENCE,
    detect_sheet_type,
    sheet_understanding_payload,
    suggest_mapping_with_confidence,
)
from app.services.settings import get_brand_config, patch_brand_config
from app.tasks.uploads import process_upload_with_fallback
from app.utils.csv_parser import dataframe_to_csv_bytes, dataframes_from_upload
from app.utils.s3 import save_upload_file

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


def _progress_redis_client() -> redis.Redis | None:
    url = os.getenv("REDIS_URL")
    host = os.getenv("REDIS_HOST")
    if not url and not host:
        return None

    try:
        if url:
            return redis.Redis.from_url(url, decode_responses=True)
        return redis.Redis(
            host=host or "redis",
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
    except Exception:
        return None


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    upload_type: UploadType = Form(...),
    column_mapping_json: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    content = await file.read()
    upload_type_key = upload_type.value

    if upload_type_key in UPLOAD_FIELD_ALIASES:
        try:
            fname = (file.filename or "").lower()
            if fname.endswith((".xlsx", ".xlsm")):
                try:
                    sheets = pd.read_excel(BytesIO(content), sheet_name=None)
                    incoming_df = next(iter(sheets.values()))
                except Exception:
                    # Some user files are CSV content with an .xlsx suffix.
                    incoming_df = pd.read_csv(BytesIO(content))
            else:
                incoming_df = pd.read_csv(BytesIO(content))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "Unable to parse file. Please upload CSV or XLSX.",
                    "details": str(exc),
                },
            ) from exc

        config = await get_brand_config(db, current_user.brand_id)
        stored_mapping = (
            (config.get("column_mappings") or {}).get(upload_type_key)
            if isinstance(config, dict)
            else None
        )
        manual_mapping = None
        if column_mapping_json:
            try:
                decoded = json.loads(column_mapping_json)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "VALIDATION_ERROR",
                        "message": "column_mapping_json must be valid JSON",
                        "details": str(exc),
                    },
                ) from exc
            if isinstance(decoded, dict):
                manual_mapping = {str(k): str(v) for k, v in decoded.items()}

        try:
            mapping = resolve_column_mapping(
                upload_type=upload_type_key,
                df_columns=list(incoming_df.columns),
                stored_mapping=stored_mapping if isinstance(stored_mapping, dict) else None,
                manual_mapping=manual_mapping,
            )
        except MappingRequiredError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MAPPING_REQUIRED",
                    "message": "We could not automatically identify all required columns.",
                    "details": {
                        "upload_type": exc.upload_type,
                        "missing_fields": exc.missing_fields,
                        "available_columns": exc.available_columns,
                        "mappable_fields": available_fields(upload_type_key),
                    },
                },
            ) from exc

        transformed_df = apply_column_mapping(incoming_df, mapping)
        content = dataframe_to_csv_bytes(transformed_df)

        if manual_mapping is not None or not isinstance(stored_mapping, dict):
            await patch_brand_config(
                db,
                current_user.brand_id,
                {"column_mappings": {upload_type_key: mapping}},
            )

    path_or_key = save_upload_file(content, str(current_user.brand_id), upload_type.value, file.filename)
    row = Upload(
        brand_id=current_user.brand_id,
        uploaded_by=current_user.id,
        upload_type=upload_type,
        filename=file.filename,
        s3_key=path_or_key,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    task_info = await process_upload_with_fallback(str(row.id), str(current_user.brand_id))
    return envelope(
        {
            "upload_id": str(row.id),
            "status": "PENDING",
            "task_id": task_info.get("task_id"),
            "mode": task_info.get("mode"),
        }
    )


@router.post("/smart-upload")
async def smart_upload(
    file: UploadFile = File(...),
    sheet_mapping_json: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.PLANNER)),
) -> dict:
    content = await file.read()
    try:
        sheets = dataframes_from_upload(content, file.filename)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Unable to parse upload file. Please upload CSV or XLSX.",
                "details": str(exc),
            },
        ) from exc

    if not sheets:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "No readable sheets found in uploaded file.",
            },
        )

    manual_by_sheet: dict[str, dict] = {}
    if sheet_mapping_json:
        try:
            decoded = json.loads(sheet_mapping_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "sheet_mapping_json must be valid JSON",
                    "details": str(exc),
                },
            ) from exc
        if isinstance(decoded, dict):
            manual_by_sheet = {
                str(sheet): value for sheet, value in decoded.items() if isinstance(value, dict)
            }

    config = await get_brand_config(db, current_user.brand_id)
    stored_column_mappings = config.get("column_mappings") if isinstance(config, dict) else {}
    stored_column_mappings = stored_column_mappings if isinstance(stored_column_mappings, dict) else {}

    understanding_items: list[dict] = []
    pending_items: list[dict] = []
    transformed_sheets: list[tuple[str, UploadType, bytes, dict[str, str], float]] = []

    for sheet_name, df in sheets.items():
        columns = [str(column) for column in df.columns]
        detection = detect_sheet_type(sheet_name=sheet_name, df_columns=columns)
        upload_type = detection.upload_type
        sheet_manual = manual_by_sheet.get(sheet_name, {})
        if sheet_manual.get("skip") is True:
            understanding_items.append(
                {
                    "sheet_name": sheet_name,
                    "detected_sheet_type": detection.sheet_type,
                    "detected_upload_type": upload_type,
                    "classifier_confidence": detection.confidence,
                    "requires_confirmation": False,
                    "skipped": True,
                    "available_columns": columns,
                }
            )
            continue

        if isinstance(sheet_manual.get("upload_type"), str):
            manual_upload_type = str(sheet_manual["upload_type"]).strip().upper()
            if manual_upload_type in UploadType.__members__:
                detection.upload_type = manual_upload_type
                upload_type = manual_upload_type

        if upload_type is None:
            understanding_items.append(
                {
                    "sheet_name": sheet_name,
                    "detected_sheet_type": detection.sheet_type,
                    "detected_upload_type": None,
                    "classifier_confidence": detection.confidence,
                    "requires_confirmation": False,
                    "skipped": True,
                    "available_columns": columns,
                }
            )
            continue

        if upload_type not in UPLOAD_FIELD_ALIASES:
            understanding_items.append(
                {
                    "sheet_name": sheet_name,
                    "detected_sheet_type": detection.sheet_type,
                    "detected_upload_type": upload_type,
                    "classifier_confidence": detection.confidence,
                    "requires_confirmation": False,
                    "skipped": True,
                    "available_columns": columns,
                    "reason": f"Upload type {upload_type} is not enabled for auto-mapping.",
                }
            )
            continue

        stored_mapping = stored_column_mappings.get(upload_type)
        manual_mapping = sheet_manual.get("mapping")
        if not isinstance(stored_mapping, dict):
            stored_mapping = None
        if not isinstance(manual_mapping, dict):
            manual_mapping = None

        mapping, field_confidence, missing_fields, low_confidence_required_fields = (
            suggest_mapping_with_confidence(
                upload_type=upload_type,
                df_columns=columns,
                stored_mapping=stored_mapping,
                manual_mapping=manual_mapping,
            )
        )
        payload = sheet_understanding_payload(
            detection=detection,
            upload_type=upload_type,
            columns=columns,
            mapping=mapping,
            confidence=field_confidence,
            missing_required=missing_fields,
            low_conf_required=low_confidence_required_fields,
        )
        understanding_items.append(payload)
        if payload["requires_confirmation"]:
            pending_items.append(payload)
            continue

        transformed_df = apply_column_mapping(df, mapping)
        transformed_sheets.append(
            (
                sheet_name,
                UploadType[detection.upload_type],
                dataframe_to_csv_bytes(transformed_df),
                mapping,
                float(payload["mapping_confidence"]),
            )
        )

    if pending_items:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MAPPING_REQUIRED",
                "message": "We could not confidently map all required fields.",
                "details": {
                    "file_name": file.filename,
                    "min_confidence": DATA_UNDERSTANDING_MIN_CONFIDENCE,
                    "sheets": pending_items,
                },
            },
        )

    if not transformed_sheets:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "No supported sheets were detected for ingestion.",
                "details": {"sheets": understanding_items},
            },
        )

    mapping_patch: dict[str, dict[str, str]] = {}
    created_rows: list[Upload] = []

    for sheet_name, upload_type, transformed_bytes, mapping, mapping_confidence in transformed_sheets:
        mapping_patch[upload_type.value] = mapping
        sheet_filename = f"{Path(file.filename).stem}__{sheet_name}.csv"
        path_or_key = save_upload_file(
            transformed_bytes,
            str(current_user.brand_id),
            upload_type.value,
            sheet_filename,
        )
        row = Upload(
            brand_id=current_user.brand_id,
            uploaded_by=current_user.id,
            upload_type=upload_type,
            filename=sheet_filename,
            s3_key=path_or_key,
            error_summary={
                "sheet_name": sheet_name,
                "mapping_confidence": mapping_confidence,
            },
        )
        db.add(row)
        created_rows.append(row)

    if mapping_patch:
        await patch_brand_config(
            db,
            current_user.brand_id,
            {"column_mappings": mapping_patch},
        )

    await db.commit()

    for row in created_rows:
        await db.refresh(row)

    task_infos = await asyncio.gather(
        *[
            process_upload_with_fallback(str(row.id), str(current_user.brand_id))
            for row in created_rows
        ]
    )

    queued: list[dict[str, str]] = []
    for row, task_info in zip(created_rows, task_infos, strict=True):
        queued.append(
            {
                "upload_id": str(row.id),
                "upload_type": row.upload_type.value,
                "filename": row.filename,
                "status": row.status.value,
                "task_id": task_info.get("task_id") or "",
                "mode": task_info.get("mode") or "",
            }
        )

    return envelope(
        {
            "file_name": file.filename,
            "queued_uploads": queued,
            "sheets": understanding_items,
        }
    )


@router.get("/uploads")
async def list_uploads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    offset = (page - 1) * page_size
    total = await db.scalar(select(func.count(Upload.id)).where(Upload.brand_id == current_user.brand_id))
    rows = (
        await db.execute(
            select(Upload)
            .where(Upload.brand_id == current_user.brand_id)
            .order_by(Upload.created_at.desc())
            .limit(page_size)
            .offset(offset)
        )
    ).scalars().all()
    return envelope(rows, meta={"page": page, "per_page": page_size, "total": int(total or 0)})


@router.get("/uploads/{task_id}/progress")
async def get_upload_progress(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    del current_user
    client = _progress_redis_client()
    if client is None:
        return envelope(
            {
                "task_id": task_id,
                "status": "PENDING",
                "stage": "queued",
                "processed": 0,
                "total": 0,
                "message": "Progress backend unavailable",
            }
        )

    raw_payload = client.get(f"ingestion_progress:{task_id}")
    if not raw_payload:
        return envelope(
            {
                "task_id": task_id,
                "status": "PENDING",
                "stage": "queued",
                "processed": 0,
                "total": 0,
                "message": "Queued for processing",
            }
        )

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        payload = {
            "task_id": task_id,
            "status": "PENDING",
            "stage": "queued",
            "processed": 0,
            "total": 0,
            "message": "Invalid progress payload",
        }

    return envelope(payload)


@router.get("/uploads/{upload_id}")
async def get_upload(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    row = await db.get(Upload, upload_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Upload not found"})
    return envelope(row)


@router.get("/uploads/{upload_id}/errors")
async def get_upload_errors(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.get(Upload, upload_id)
    if row is None or row.brand_id != current_user.brand_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Upload not found"})

    error_path = (row.error_summary or {}).get("error_report_path")
    if not error_path:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "No error report"})

    path = Path(error_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Error report missing"})

    return FileResponse(path=path, media_type="text/csv", filename=path.name)


@router.get("/data-quality")
async def data_quality(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pre-flight readiness probe.

    Inspects the data the planner has uploaded so far and flags whether the
    allocation engine has enough signal to produce a healthy run. We compute
    these checks *before* allocation so the planner can fix inputs without
    burning a full engine cycle. Each check returns ``GREEN`` / ``AMBER`` /
    ``RED`` plus a sentence the UI can render verbatim.

    Retail data is messy by definition — the bar here is "does the engine
    have enough to produce a defensible plan?", not "is every cell perfect?"
    """
    bid = current_user.brand_id

    # ── Counts ──────────────────────────────────────────────────────────
    sku_count = await db.scalar(select(func.count(SKU.id)).where(SKU.brand_id == bid)) or 0
    sku_with_band = (
        await db.scalar(
            select(func.count(SKU.id)).where(
                SKU.brand_id == bid, SKU.price_band.is_not(None)
            )
        )
        or 0
    )
    sales_rows = (
        await db.scalar(select(func.count(SalesData.id)).where(SalesData.brand_id == bid)) or 0
    )
    distinct_weeks = (
        await db.scalar(
            select(func.count(func.distinct(SalesData.week_start_date))).where(
                SalesData.brand_id == bid
            )
        )
        or 0
    )
    store_count = (
        await db.scalar(select(func.count(Store.id)).where(Store.brand_id == bid)) or 0
    )
    grade_rows = (
        await db.scalar(
            select(func.count(StoreProductGrade.id)).where(StoreProductGrade.brand_id == bid)
        )
        or 0
    )
    size_guide_rows = (
        await db.scalar(select(func.count(SizeGuide.id)).where(SizeGuide.brand_id == bid)) or 0
    )
    bridge_rows = (
        await db.scalar(
            select(func.count(StoreCategoryDemand.id)).where(StoreCategoryDemand.brand_id == bid)
        )
        or 0
    )

    # SKU overlap with sales — the cold-start canary. We compare distinct
    # SKUs in SKU master against distinct SKUs that have sales rows.
    overlap_pct: float | None = None
    if sku_count > 0:
        skus_with_sales = (
            await db.scalar(
                select(func.count(func.distinct(SalesData.sku_id))).where(
                    SalesData.brand_id == bid
                )
            )
            or 0
        )
        overlap_pct = round(skus_with_sales / sku_count, 4)

    # Stores covered by grades — anything missing grades will fall to default.
    grade_store_pct: float | None = None
    if store_count > 0:
        stores_with_grades = (
            await db.scalar(
                select(func.count(func.distinct(StoreProductGrade.store_id))).where(
                    StoreProductGrade.brand_id == bid
                )
            )
            or 0
        )
        grade_store_pct = round(stores_with_grades / store_count, 4)

    # ── Per-section verdict ─────────────────────────────────────────────
    checks: list[dict] = []

    # Sales coverage
    if distinct_weeks == 0:
        checks.append({
            "key": "sales",
            "status": "RED",
            "title": "No sales history",
            "detail": "Upload at least 8 weeks of weekly sales data to give the engine a real demand signal.",
        })
    elif distinct_weeks < 4:
        checks.append({
            "key": "sales",
            "status": "AMBER",
            "title": f"Only {distinct_weeks} week{'s' if distinct_weeks != 1 else ''} of sales",
            "detail": "Engine will rely heavily on the category-bridge fallback. Aim for 8+ weeks for HIGH-confidence lines.",
        })
    elif distinct_weeks < 8:
        checks.append({
            "key": "sales",
            "status": "AMBER",
            "title": f"{distinct_weeks} weeks of sales (8+ recommended)",
            "detail": "Bridge will fill gaps but expect some MEDIUM-confidence lines.",
        })
    else:
        checks.append({
            "key": "sales",
            "status": "GREEN",
            "title": f"{distinct_weeks} weeks of sales · {sales_rows:,} rows",
            "detail": "Demand engine has enough temporal signal.",
        })

    # SKU ↔ sales overlap
    if overlap_pct is None:
        checks.append({
            "key": "sku_overlap",
            "status": "AMBER",
            "title": "Upload a buy file to compute SKU overlap",
            "detail": "Engine needs both sides (SKU master + sales) to know whether the bridge will be used.",
        })
    elif overlap_pct < 0.05:
        checks.append({
            "key": "sku_overlap",
            "status": "RED",
            "title": f"Only {overlap_pct * 100:.1f}% of SKUs have sales history",
            "detail": (
                "Buy file styles barely overlap with sales. Engine will lean on the "
                "category × price-band bridge for almost every line — expect mostly "
                "MEDIUM-confidence allocation. To get HIGH-confidence lines, ensure "
                "buy file styles share codes with prior-season sales."
            ),
        })
    elif overlap_pct < 0.30:
        checks.append({
            "key": "sku_overlap",
            "status": "AMBER",
            "title": f"{overlap_pct * 100:.1f}% SKU ↔ sales overlap",
            "detail": "Bridge will carry the bulk of demand. Acceptable for a cold-start cycle.",
        })
    else:
        checks.append({
            "key": "sku_overlap",
            "status": "GREEN",
            "title": f"{overlap_pct * 100:.1f}% SKU ↔ sales overlap",
            "detail": "Most lines will resolve to per-SKU or per-cluster history.",
        })

    # Store grades
    if grade_store_pct is None:
        checks.append({
            "key": "grades",
            "status": "AMBER",
            "title": "No stores yet",
            "detail": "Upload store grades — they bootstrap your stores and tier the allocation.",
        })
    elif grade_store_pct < 0.7:
        checks.append({
            "key": "grades",
            "status": "AMBER",
            "title": f"Only {grade_store_pct * 100:.0f}% of stores have grades",
            "detail": "Stores without grades fall back to grade C, which dampens their allocation.",
        })
    else:
        checks.append({
            "key": "grades",
            "status": "GREEN",
            "title": f"{grade_store_pct * 100:.0f}% of stores graded",
            "detail": "Grade-tier multipliers will apply across the network.",
        })

    # Size guide
    if size_guide_rows == 0:
        checks.append({
            "key": "size_guide",
            "status": "AMBER",
            "title": "No size guide uploaded",
            "detail": "Engine can still allocate, but size split will fall to a uniform default.",
        })
    else:
        checks.append({
            "key": "size_guide",
            "status": "GREEN",
            "title": f"{size_guide_rows} size-guide rows",
            "detail": "Pivotal vs non-pivotal split will be applied per category.",
        })

    # Price-band coverage on the buy file
    if sku_count > 0:
        band_pct = sku_with_band / sku_count
        if band_pct < 0.8:
            checks.append({
                "key": "price_bands",
                "status": "AMBER",
                "title": f"{band_pct * 100:.0f}% of SKUs have a price band",
                "detail": "Bridge keys on (category × price band). SKUs without bands won't benefit from per-band signal.",
            })
        else:
            checks.append({
                "key": "price_bands",
                "status": "GREEN",
                "title": f"{band_pct * 100:.0f}% of SKUs have price bands",
                "detail": "Bridge can resolve at full granularity.",
            })

    # Bridge readiness
    if bridge_rows == 0 and (sales_rows > 0 and sku_count > 0):
        checks.append({
            "key": "bridge",
            "status": "AMBER",
            "title": "Category bridge not yet built",
            "detail": "Re-run sales ingestion (or trigger a backfill) so the engine has the bridge ready before allocation.",
        })
    elif bridge_rows > 0:
        checks.append({
            "key": "bridge",
            "status": "GREEN",
            "title": f"Bridge built · {bridge_rows} (store × category × band) cells",
            "detail": "Cold-start lines will use the bridge instead of falling to minimum-presentation.",
        })

    # ── Overall readiness ──────────────────────────────────────────────
    statuses = {check["status"] for check in checks}
    if "RED" in statuses:
        readiness = "RED"
        readiness_message = "Fix the red items before running allocation — engine will produce a low-quality result."
    elif "AMBER" in statuses:
        readiness = "AMBER"
        readiness_message = (
            "Allocation will run but expect mixed confidence. Review the amber items if you "
            "want a HIGH-confidence plan."
        )
    else:
        readiness = "GREEN"
        readiness_message = "All inputs look healthy — allocation should land in the APPROVE band."

    return envelope(
        {
            "readiness": readiness,
            "readiness_message": readiness_message,
            "checks": checks,
            "facts": {
                "skus": int(sku_count),
                "sku_overlap_with_sales_pct": overlap_pct,
                "sales_rows": int(sales_rows),
                "distinct_weeks_of_sales": int(distinct_weeks),
                "stores": int(store_count),
                "grade_store_coverage_pct": grade_store_pct,
                "size_guide_rows": int(size_guide_rows),
                "bridge_rows": int(bridge_rows),
            },
        }
    )
