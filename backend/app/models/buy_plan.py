from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BuyPlanFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buy_plan_files"
    __table_args__ = (
        Index("idx_buy_plan_files_brand_id", "brand_id"),
        UniqueConstraint("brand_id", "name", name="uq_buy_plan_files_brand_name"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    upload_id: Mapped[UUID | None] = mapped_column(ForeignKey("uploads.id"))
    season_id: Mapped[UUID | None] = mapped_column(ForeignKey("seasons.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class BuyPlanLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buy_plan_lines"
    __table_args__ = (
        Index("idx_buy_plan_lines_buy_plan_file", "buy_plan_file_id"),
        Index("idx_buy_plan_lines_brand_sku", "brand_id", "sku_id"),
        UniqueConstraint(
            "buy_plan_file_id",
            "sku_id",
            "store_group_rule",
            name="uq_buy_plan_lines_file_sku_group",
        ),
    )

    buy_plan_file_id: Mapped[UUID] = mapped_column(ForeignKey("buy_plan_files.id"), nullable=False)
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("skus.id"), nullable=False)
    store_group_rule: Mapped[str | None] = mapped_column(String(200))
    style_risk_group: Mapped[str | None] = mapped_column(String(50))
    total_buy_qty: Mapped[int | None] = mapped_column(Integer)
    expected_first_allocation_qty: Mapped[int | None] = mapped_column(Integer)
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    expected_delivery_week: Mapped[date | None] = mapped_column(Date)
    planned_cost_per_unit: Mapped[float | None] = mapped_column(Numeric(10, 2))
    moq: Mapped[int | None] = mapped_column(Integer)
    planned_price_per_unit: Mapped[float | None] = mapped_column(Numeric(10, 2))
    planned_margin_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
