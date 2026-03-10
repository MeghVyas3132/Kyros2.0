import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AlertType(str, enum.Enum):
    STOCKOUT_RISK = "STOCKOUT_RISK"
    AGING_STOCK = "AGING_STOCK"
    GRN_UNALLOCATED = "GRN_UNALLOCATED"


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("idx_alerts_brand_active", "brand_id", "is_dismissed", "generated_at"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType, name="alert_type"), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    store_id: Mapped[UUID | None] = mapped_column(ForeignKey("stores.id"))
    sku_id: Mapped[UUID | None] = mapped_column(ForeignKey("skus.id"))
    grn_id: Mapped[UUID | None] = mapped_column(ForeignKey("grns.id"))
    season_id: Mapped[UUID | None] = mapped_column(ForeignKey("seasons.id"))
    action_url: Mapped[str | None] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
