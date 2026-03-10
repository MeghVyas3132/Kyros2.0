from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SKUBase(BaseModel):
    sku_code: str
    style_code: str
    style_name: str
    category: str
    sub_category: str | None = None
    fabric: str | None = None
    colour: str | None = None
    colour_family: str | None = None
    price_band: str | None = None
    mrp: float | None = None
    cost_price: float | None = None
    size: str | None = None
    fit_type: str | None = None
    sku_type: str = "FASHION"
    season_id: UUID | None = None
    is_active: bool = True


class SKUCreate(SKUBase):
    pass


class SKUUpdate(BaseModel):
    style_code: str | None = None
    style_name: str | None = None
    category: str | None = None
    sub_category: str | None = None
    fabric: str | None = None
    colour: str | None = None
    colour_family: str | None = None
    price_band: str | None = None
    mrp: float | None = None
    cost_price: float | None = None
    size: str | None = None
    fit_type: str | None = None
    sku_type: str | None = None
    season_id: UUID | None = None
    is_active: bool | None = None


class SKUOut(SKUBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    created_at: datetime
    updated_at: datetime
