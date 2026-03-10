from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InventoryReservationType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_reservation_types"
    __table_args__ = (
        UniqueConstraint("brand_id", "code", name="uq_inventory_reservation_types_brand_code"),
        Index("idx_inventory_reservation_types_brand_id", "brand_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    deducts_from_first_allocation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class GRNLineReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grn_line_reservations"
    __table_args__ = (
        UniqueConstraint("grn_line_id", "reservation_type_id", name="uq_grn_line_reservations_unique"),
        Index("idx_grn_line_reservations_line_id", "grn_line_id"),
    )

    grn_line_id: Mapped[UUID] = mapped_column(ForeignKey("grn_lines.id"), nullable=False)
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    reservation_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_reservation_types.id"), nullable=False
    )
    reserved_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
