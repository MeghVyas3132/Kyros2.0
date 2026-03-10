from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SalesData(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_data"
    __table_args__ = (
        UniqueConstraint(
            "brand_id", "store_id", "sku_id", "week_start_date", name="uq_sales_brand_store_sku_week"
        ),
        Index("idx_sales_brand_store_sku", "brand_id", "store_id", "sku_id"),
        Index("idx_sales_week", "brand_id", "week_start_date"),
        Index("idx_sales_sku", "brand_id", "sku_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    upload_id: Mapped[UUID | None] = mapped_column(ForeignKey("uploads.id"))
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id"), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("skus.id"), nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    was_on_promotion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    was_in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
