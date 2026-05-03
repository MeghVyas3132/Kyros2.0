"""Self-serve signup queue.

A pilot brand fills the signup form on the public website. We persist a
``SignupRequest`` row in PENDING state instead of creating the Brand + User
directly. The platform's ``SUPER_ADMIN`` then reviews the queue and either:

  - APPROVE → we create the Brand + BrandSettings + User (role=ADMIN) using
    the credentials captured at signup time. The applicant can log in
    immediately afterwards.
  - REJECT  → the row is marked REJECTED (or hard-deleted by the SUPER_ADMIN).

This file deliberately keeps signup data isolated from the live
``users`` / ``brands`` tables so an unreviewed application can never grant
access to anything inside Kyros.
"""
from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SignupRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SignupRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "signup_requests"
    __table_args__ = (
        UniqueConstraint("email", name="uq_signup_requests_email"),
        UniqueConstraint("brand_slug", name="uq_signup_requests_brand_slug"),
        Index("idx_signup_requests_status", "status"),
    )

    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    company_size: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[SignupRequestStatus] = mapped_column(
        Enum(SignupRequestStatus, name="signup_request_status"),
        nullable=False,
        default=SignupRequestStatus.PENDING,
        server_default=SignupRequestStatus.PENDING.value,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_brand_id: Mapped[UUID | None] = mapped_column(ForeignKey("brands.id"))
    created_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
