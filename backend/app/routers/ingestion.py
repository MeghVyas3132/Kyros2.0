import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from io import BytesIO

import pandas as pd
import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import Upload, UploadType, User, UserRole
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
                sheets = pd.read_excel(BytesIO(content), sheet_name=None)
                incoming_df = next(iter(sheets.values()))
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
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    rows = (
        await db.execute(select(Upload).where(Upload.brand_id == current_user.brand_id).order_by(Upload.created_at.desc()))
    ).scalars().all()
    return envelope(rows)


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
