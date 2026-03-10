from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OnboardingSettingsPatch(BaseModel):
    config_patch: dict = Field(default_factory=dict)


class ColumnMappingPayload(BaseModel):
    mapping: dict[str, str]


class ReservationTypeCreate(BaseModel):
    code: str
    label: str
    deducts_from_first_allocation: bool = True
    display_order: int = 0
    is_active: bool = True


class ReservationTypeUpdate(BaseModel):
    label: str | None = None
    deducts_from_first_allocation: bool | None = None
    display_order: int | None = None
    is_active: bool | None = None


class ReservationTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    code: str
    label: str
    deducts_from_first_allocation: bool
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
