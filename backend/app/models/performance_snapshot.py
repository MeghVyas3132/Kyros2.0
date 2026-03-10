from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PerformanceSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "brand_id", "snapshot_date", "store_id", "sku_id", name="uq_perf_snapshot_brand_date_store_sku"
        ),
        Index("idx_perf_snap_brand_date", "brand_id", "snapshot_date"),
        Index("idx_perf_snap_sku", "brand_id", "sku_id", "snapshot_date"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    season_id: Mapped[UUID | None] = mapped_column(ForeignKey("seasons.id"))
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id"), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("skus.id"), nullable=False)
    units_sold_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_sold_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_sold_28d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sell_through_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    ros_7d: Mapped[float | None] = mapped_column(Numeric(8, 2))
    stock_cover_days: Mapped[float | None] = mapped_column(Numeric(8, 1))
    days_since_grn: Mapped[int | None] = mapped_column(Integer)
    style_status: Mapped[str | None] = mapped_column(String(20))
    is_stockout: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lost_sales_estimate: Mapped[float | None] = mapped_column(Numeric(8, 2))
