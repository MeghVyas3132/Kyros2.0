from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StyleStoreList(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "style_store_lists"
    __table_args__ = (
        UniqueConstraint("brand_id", "list_name", name="uq_style_store_lists_brand_name"),
        Index("idx_style_store_lists_brand_id", "brand_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    list_name: Mapped[str] = mapped_column(String(100), nullable=False)
    store_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False)


class SKU(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "skus"
    __table_args__ = (
        UniqueConstraint("brand_id", "sku_code", name="uq_skus_brand_sku_code"),
        Index("idx_skus_brand_id", "brand_id"),
        Index("idx_skus_style_code", "brand_id", "style_code"),
        Index("idx_skus_category", "brand_id", "category"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(100), nullable=False)
    style_code: Mapped[str] = mapped_column(String(100), nullable=False)
    style_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(100))
    fabric: Mapped[str | None] = mapped_column(String(100))
    colour: Mapped[str | None] = mapped_column(String(100))
    colour_family: Mapped[str | None] = mapped_column(String(50))
    price_band: Mapped[str | None] = mapped_column(String(50))
    mrp: Mapped[float | None] = mapped_column(Numeric(10, 2))
    cost_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    size: Mapped[str | None] = mapped_column(String(20))
    fit_type: Mapped[str | None] = mapped_column(String(50))
    sku_type: Mapped[str] = mapped_column(String(20), nullable=False, default="FASHION")
    season_id: Mapped[UUID | None] = mapped_column(ForeignKey("seasons.id"))
    store_group_rule: Mapped[str | None] = mapped_column(String(200))
    resolved_min_grade: Mapped[str | None] = mapped_column(String(10))
    style_risk_group: Mapped[str | None] = mapped_column(String(50))
    resolved_risk_level: Mapped[str | None] = mapped_column(String(20))
    story: Mapped[str | None] = mapped_column(String(200))
    sub_story: Mapped[str | None] = mapped_column(String(200))
    buyer_name: Mapped[str | None] = mapped_column(String(200))
    vendor_name: Mapped[str | None] = mapped_column(String(200))
    store_list_id: Mapped[UUID | None] = mapped_column(ForeignKey("style_store_lists.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
