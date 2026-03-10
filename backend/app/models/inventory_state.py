from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InventoryState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_state"
    __table_args__ = (
        UniqueConstraint(
            "brand_id",
            "snapshot_date",
            "location_id",
            "location_type",
            "sku_id",
            name="uq_inventory_state_unique",
        ),
        Index("idx_inv_state_latest", "brand_id", "snapshot_date"),
        Index("idx_inv_state_location", "brand_id", "location_id", "snapshot_date"),
        Index("idx_inv_state_sku", "brand_id", "sku_id", "snapshot_date"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    location_id: Mapped[str] = mapped_column(String(100), nullable=False)
    location_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("skus.id"), nullable=False)
    units_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_in_transit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_sold_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_sold_28d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ros_7d: Mapped[float | None] = mapped_column(Numeric(8, 2))
    ros_28d: Mapped[float | None] = mapped_column(Numeric(8, 2))
    stock_cover_days: Mapped[float | None] = mapped_column(Numeric(8, 1))
    days_since_grn: Mapped[int | None] = mapped_column(Integer)
    days_since_first_sale: Mapped[int | None] = mapped_column(Integer)
    sell_through_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    is_stockout: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_new_arrival: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
