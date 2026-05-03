"""Category × price-band demand bridge.

The allocation engine's demand cascade is:

    store-history → cluster-history → category-bridge → grade-fallback → minimum

Without this table the cascade jumps straight from cluster to grade-fallback
and ends up at minimum-presentation for every cold-start SKU. With it, a
brand-new SS26 style inherits the *aggregated* sell-velocity that the same
``(store, category, price_band)`` cell showed in prior seasons.

We deliberately store the aggregation (not the raw rows) because:

  * lookups are hot-path during allocation (one row per (store × sku))
  * the aggregation is computed once at sales ingestion, not per-allocation
  * we want a single canonical place that says "this store sold X kurtas/wk
    in the ₹2-3K band last season" — independent of which SKU codes came in.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreCategoryDemand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_category_demand"
    __table_args__ = (
        UniqueConstraint(
            "brand_id",
            "store_id",
            "category",
            "price_band",
            name="uq_store_category_demand_unique",
        ),
        Index(
            "idx_store_category_demand_lookup",
            "brand_id",
            "store_id",
            "category",
            "price_band",
        ),
        Index("idx_store_category_demand_brand", "brand_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    # price_band uses a sentinel "*" when the source data has no band — never NULL,
    # so the unique constraint behaves the same as exact-match elsewhere in the engine.
    price_band: Mapped[str] = mapped_column(String(100), nullable=False, default="*")
    weekly_ros: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    units_observed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weeks_observed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_observed_week: Mapped[date | None] = mapped_column(Date)
    sample_skus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
