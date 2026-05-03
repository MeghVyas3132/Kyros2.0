from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BootstrapStatusResponse(BaseModel):
    bootstrap_required: bool
    user_count: int


class BootstrapRequest(BaseModel):
    brand_name: str = Field(min_length=2, max_length=255)
    brand_slug: str | None = Field(default=None, min_length=2, max_length=100)
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    initial_config: dict = Field(default_factory=dict)


class SignupRequestCreate(BaseModel):
    """Public-facing signup payload. Same shape as BootstrapRequest minus the
    bootstrap-only `initial_config` field, plus a few demographics the
    super-admin uses to decide whether to onboard."""

    brand_name: str = Field(min_length=2, max_length=255)
    brand_slug: str | None = Field(default=None, min_length=2, max_length=100)
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=50)
    company_size: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class SignupRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_name: str
    brand_slug: str
    full_name: str
    email: EmailStr
    contact_phone: str | None
    company_size: str | None
    notes: str | None
    status: str
    reviewed_at: datetime | None
    reviewed_by: UUID | None
    created_brand_id: UUID | None
    created_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
