import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UploadType(str, enum.Enum):
    SALES = "SALES"
    INVENTORY = "INVENTORY"
    GRN = "GRN"
    STORE_MASTER = "STORE_MASTER"
    SKU_MASTER = "SKU_MASTER"
    STORE_GRADES = "STORE_GRADES"
    SIZE_GUIDE = "SIZE_GUIDE"
    BUY_FILE = "BUY_FILE"
    RESERVATION_TYPES = "RESERVATION_TYPES"


class UploadStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class Upload(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "uploads"
    __table_args__ = (Index("idx_uploads_brand_id", "brand_id"),)

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    upload_type: Mapped[UploadType] = mapped_column(Enum(UploadType, name="upload_type"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status"), nullable=False, default=UploadStatus.PENDING
    )
    total_rows: Mapped[int | None] = mapped_column(Integer)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[dict | None] = mapped_column(JSON)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
