from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BuyPlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    season_id: UUID | None = None
    notes: str | None = None
    source_filename: str | None = None


class BuyPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    season_id: UUID | None = None
    notes: str | None = None


class BuyPlanLineCreate(BaseModel):
    sku_id: UUID
    store_group_rule: str | None = None
    style_risk_group: str | None = None
    total_buy_qty: int | None = None
    expected_first_allocation_qty: int | None = None
    vendor_name: str | None = None
    expected_delivery_week: date | None = None
    planned_cost_per_unit: float | None = None
    moq: int | None = None
    planned_price_per_unit: float | None = None
    planned_margin_pct: float | None = None


class BuyPlanLineUpdate(BaseModel):
    vendor_name: str | None = None
    expected_delivery_week: date | None = None
    planned_cost_per_unit: float | None = None
    moq: int | None = None
    planned_price_per_unit: float | None = None
    planned_margin_pct: float | None = None
    total_buy_qty: int | None = None
    store_group_rule: str | None = None
    style_risk_group: str | None = None


class BuyPlanLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    buy_plan_file_id: UUID
    brand_id: UUID
    sku_id: UUID
    sku_code: str | None = None
    style_code: str | None = None
    style_name: str | None = None
    category: str | None = None
    size: str | None = None
    colour: str | None = None
    price_band: str | None = None
    store_group_rule: str | None = None
    style_risk_group: str | None = None
    total_buy_qty: int | None = None
    expected_first_allocation_qty: int | None = None
    vendor_name: str | None = None
    expected_delivery_week: date | None = None
    planned_cost_per_unit: float | None = None
    moq: int | None = None
    planned_price_per_unit: float | None = None
    planned_margin_pct: float | None = None
    created_at: datetime
    updated_at: datetime


class BuyPlanFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    season_id: UUID | None = None
    name: str
    source_filename: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class BuyPlanFileWithStats(BuyPlanFileOut):
    total_lines: int = 0
    total_units: int = 0
    total_styles: int = 0
    categories: list[str] = []


class OTBReconciliationRow(BaseModel):
    category: str
    month: str
    planned_sales: float
    otb_value: float
    buy_plan_cost: float
    otb_usage_pct: float
    is_overrun: bool


class BuyPlanReconciliation(BaseModel):
    buy_plan_file_id: UUID
    season_id: UUID | None = None
    rows: list[OTBReconciliationRow]
    total_otb: float
    total_committed: float
    overall_usage_pct: float
