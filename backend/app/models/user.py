import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    PLANNER = "PLANNER"
    VIEWER = "VIEWER"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_brand_id", "brand_id"),
        Index("idx_users_email", "email"),
    )

    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
