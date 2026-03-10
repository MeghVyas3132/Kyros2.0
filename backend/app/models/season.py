import enum
from datetime import date
from uuid import UUID

from sqlalchemy import ARRAY, Computed, Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SeasonStatus(str, enum.Enum):
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class Season(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "seasons"

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    categories: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    status: Mapped[SeasonStatus] = mapped_column(
        Enum(SeasonStatus, name="season_status"), default=SeasonStatus.PLANNING, nullable=False
    )


class SeasonOTB(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "season_otb"
    __table_args__ = (
        UniqueConstraint("season_id", "category", "month", name="uq_season_otb_unique"),
    )

    season_id: Mapped[UUID] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    planned_sales: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    planned_closing_stock: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    opening_stock: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    on_order: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    otb_value: Mapped[float] = mapped_column(
        Numeric(12, 2),
        Computed("planned_sales + planned_closing_stock - opening_stock - on_order", persisted=True),
    )
