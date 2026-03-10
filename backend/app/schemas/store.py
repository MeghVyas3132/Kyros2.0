from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StoreBase(BaseModel):
    store_code: str
    store_name: str
    city: str | None = None
    state: str | None = None
    cluster_id: UUID | None = None
    store_type: str | None = None
    climate_zone: str | None = None
    is_active: bool = True
    opening_date: date | None = None


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    store_name: str | None = None
    city: str | None = None
    state: str | None = None
    cluster_id: UUID | None = None
    store_type: str | None = None
    climate_zone: str | None = None
    is_active: bool | None = None
    opening_date: date | None = None


class StoreOut(StoreBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    created_at: datetime
    updated_at: datetime


class StoreCapacityBase(BaseModel):
    store_id: UUID
    category: str
    max_styles: int
    max_units: int | None = None


class StoreCapacityCreate(StoreCapacityBase):
    pass


class StoreCapacityUpdate(BaseModel):
    category: str | None = None
    max_styles: int | None = None
    max_units: int | None = None


class StoreCapacityOut(StoreCapacityBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    created_at: datetime
    updated_at: datetime
