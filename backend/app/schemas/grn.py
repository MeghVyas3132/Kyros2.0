from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GRNLineCreate(BaseModel):
    sku_id: UUID
    units_received: int


class GRNCreate(BaseModel):
    grn_code: str
    grn_date: date
    warehouse_id: str | None = None
    supplier_name: str | None = None
    season_id: UUID | None = None
    lines: list[GRNLineCreate]


class GRNLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    grn_id: UUID
    brand_id: UUID
    sku_id: UUID
    units_received: int
    created_at: datetime
    updated_at: datetime


class GRNOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    grn_code: str
    grn_date: date
    warehouse_id: str | None
    supplier_name: str | None
    status: str
    total_units: int
    total_skus: int
    season_id: UUID | None
    upload_id: UUID | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class GRNDetail(GRNOut):
    lines: list[GRNLineOut]
