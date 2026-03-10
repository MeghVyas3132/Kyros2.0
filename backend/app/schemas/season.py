from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import SeasonStatus


class SeasonBase(BaseModel):
    name: str
    start_date: date
    end_date: date
    categories: list[str] = []
    status: SeasonStatus = SeasonStatus.PLANNING


class SeasonCreate(SeasonBase):
    pass


class SeasonUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    categories: list[str] | None = None
    status: SeasonStatus | None = None


class SeasonOut(SeasonBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    created_at: datetime
    updated_at: datetime


class OTBInput(BaseModel):
    category: str
    month: date
    planned_sales: float
    planned_closing_stock: float
    opening_stock: float
    on_order: float = 0


class OTBOut(OTBInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    season_id: UUID
    brand_id: UUID
    otb_value: float
    created_at: datetime
    updated_at: datetime
