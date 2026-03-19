import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AllocationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"
    CANCELLED = "CANCELLED"


class AllocationSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "allocation_sessions"

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    grn_id: Mapped[UUID] = mapped_column(ForeignKey("grns.id"), nullable=False)
    season_id: Mapped[UUID | None] = mapped_column(ForeignKey("seasons.id"))
    status: Mapped[AllocationStatus] = mapped_column(
        Enum(AllocationStatus, name="allocation_status"), nullable=False, default=AllocationStatus.DRAFT
    )
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_by_user: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    total_stores: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_skus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_units_recommended: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_units_approved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AllocationLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "allocation_lines"
    __table_args__ = (
        UniqueConstraint("session_id", "store_id", "sku_id", name="uq_alloc_lines_session_store_sku"),
        Index("idx_alloc_lines_session", "session_id"),
        Index("idx_alloc_lines_store", "brand_id", "store_id"),
        Index("idx_alloc_lines_sku", "brand_id", "sku_id"),
    )

    session_id: Mapped[UUID] = mapped_column(ForeignKey("allocation_sessions.id"), nullable=False)
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id"), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("skus.id"), nullable=False)
    ai_recommended_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_confidence: Mapped[str | None] = mapped_column(String(10))
    ai_reasoning: Mapped[dict] = mapped_column(JSON, nullable=False)
    ai_projections: Mapped[dict | None] = mapped_column(JSON)
    final_qty: Mapped[int | None] = mapped_column(Integer)
    was_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_reason: Mapped[str | None] = mapped_column(String(100))
    override_notes: Mapped[str | None] = mapped_column(Text)
    actual_sellthrough_4w: Mapped[float | None] = mapped_column(Numeric(5, 2))
    actual_sellthrough_8w: Mapped[float | None] = mapped_column(Numeric(5, 2))
    actual_sellthrough_eow: Mapped[float | None] = mapped_column(Numeric(5, 2))
    ai_was_better: Mapped[bool | None] = mapped_column(Boolean)
