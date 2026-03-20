from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreBehaviorProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_behavior_profiles"
    __table_args__ = (
        UniqueConstraint("brand_id", "store_id", name="uq_store_behavior_profiles_brand_store"),
        Index("idx_store_behavior_profiles_brand", "brand_id"),
        Index("idx_store_behavior_profiles_store", "store_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id"), nullable=False)

    primary_category_affinity: Mapped[str | None] = mapped_column(String(100))
    primary_fabric_affinity: Mapped[str | None] = mapped_column(String(100))

    category_affinity_score: Mapped[float | None] = mapped_column(Float)
    fabric_affinity_score: Mapped[float | None] = mapped_column(Float)

    profile_window_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=12, server_default="12")
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
