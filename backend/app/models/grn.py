from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GRN(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grns"
    __table_args__ = (
        UniqueConstraint("brand_id", "grn_code", name="uq_grns_brand_grn_code"),
        Index("idx_grns_brand_id", "brand_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    grn_code: Mapped[str] = mapped_column(String(100), nullable=False)
    grn_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[str | None] = mapped_column(String(100))
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="RECEIVED")
    total_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_skus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    season_id: Mapped[UUID | None] = mapped_column(ForeignKey("seasons.id"))
    upload_id: Mapped[UUID | None] = mapped_column(ForeignKey("uploads.id"))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class GRNLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grn_lines"
    __table_args__ = (
        Index("idx_grn_lines_grn_id", "grn_id"),
        UniqueConstraint("grn_id", "sku_id", name="uq_grn_lines_grn_sku"),
    )

    grn_id: Mapped[UUID] = mapped_column(ForeignKey("grns.id"), nullable=False)
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("skus.id"), nullable=False)
    buy_plan_line_id: Mapped[UUID | None] = mapped_column(ForeignKey("buy_plan_lines.id"))
    units_received: Mapped[int] = mapped_column(Integer, nullable=False)
    total_buy_qty: Mapped[int | None] = mapped_column(Integer)
    ecom_reserved_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ars_reserved_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
