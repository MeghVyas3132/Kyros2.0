from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import UploadStatus, UploadType


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    uploaded_by: UUID
    upload_type: UploadType
    filename: str
    s3_key: str
    status: UploadStatus
    total_rows: int | None = None
    successful_rows: int
    failed_rows: int
    error_summary: dict | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UploadStartResponse(BaseModel):
    upload_id: UUID
    status: UploadStatus
