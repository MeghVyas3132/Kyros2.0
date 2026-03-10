from uuid import UUID

from sqlalchemy import ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BrandSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brand_settings"
    __table_args__ = (
        UniqueConstraint("brand_id", name="uq_brand_settings_brand_id"),
        Index("idx_brand_settings_config_gin", "config", postgresql_using="gin"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
