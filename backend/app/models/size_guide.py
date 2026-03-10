from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SizeGuide(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "size_guides"
    __table_args__ = (
        UniqueConstraint("brand_id", "product_category", "size", name="uq_size_guides_unique"),
        Index("idx_size_guides_lookup", "brand_id", "product_category", "display_order"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    product_category: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[str] = mapped_column(String(20), nullable=False)
    size_type: Mapped[str] = mapped_column(String(20), nullable=False, default="PIVOTAL", server_default="PIVOTAL")
    min_max_ratio: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_size_set: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    applies_to_grades: Mapped[str] = mapped_column(String(20), nullable=False, default="ALL", server_default="ALL")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
