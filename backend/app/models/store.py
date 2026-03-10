from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Store(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stores"
    __table_args__ = (
        UniqueConstraint("brand_id", "store_code", name="uq_stores_brand_store_code"),
        Index("idx_stores_brand_id", "brand_id"),
        Index("idx_stores_cluster_id", "cluster_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    store_code: Mapped[str] = mapped_column(String(50), nullable=False)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    cluster_id: Mapped[UUID | None] = mapped_column(ForeignKey("clusters.id"))
    store_type: Mapped[str | None] = mapped_column(String(50))
    climate_zone: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    opening_date: Mapped[date | None] = mapped_column(Date)


class StoreDisplayCapacity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_display_capacity"
    __table_args__ = (
        UniqueConstraint("store_id", "category", name="uq_store_capacity_store_category"),
        Index("idx_store_capacity_brand_id", "brand_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    max_styles: Mapped[int] = mapped_column(Integer, nullable=False)
    max_units: Mapped[int | None] = mapped_column(Integer)


class StoreProductGrade(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_product_grades"
    __table_args__ = (
        UniqueConstraint(
            "brand_id",
            "store_id",
            "product_category",
            "price_band",
            name="uq_store_product_grades_unique",
        ),
        Index(
            "idx_store_product_grades_lookup",
            "brand_id",
            "store_id",
            "product_category",
            "price_band",
        ),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id"), nullable=False)
    product_category: Mapped[str] = mapped_column(String(100), nullable=False)
    price_band: Mapped[str | None] = mapped_column(String(100))
    grade: Mapped[str] = mapped_column(String(10), nullable=False)
