from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import AllocationStatus


class AllocationGenerateRequest(BaseModel):
    grn_id: UUID


class AllocationSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    grn_id: UUID
    season_id: UUID | None
    status: AllocationStatus
    engine_version: str
    generated_at: datetime | None
    generated_by_user: UUID | None
    total_stores: int
    total_skus: int
    total_units_recommended: int
    total_units_approved: int
    approved_by: UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AllocationLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    brand_id: UUID
    store_id: UUID
    sku_id: UUID
    ai_recommended_qty: int
    ai_confidence: str | None
    ai_reasoning: dict
    ai_projections: dict | None
    final_qty: int | None
    was_overridden: bool
    override_reason: str | None
    override_notes: str | None
    store_code: str | None = None
    store_name: str | None = None
    store_city: str | None = None
    sku_code: str | None = None
    style_name: str | None = None
    sku_size: str | None = None
    sku_category: str | None = None
    sku_fabric: str | None = None
    sku_colour: str | None = None
    sku_price_band: str | None = None
    sku_store_group_rule: str | None = None
    sku_resolved_min_grade: str | None = None
    sku_style_risk_group: str | None = None
    sku_resolved_risk_level: str | None = None
    sku_story: str | None = None
    sku_sub_story: str | None = None
    grn_units_received: int | None = None
    grn_total_buy_qty: int | None = None
    grn_ecom_reserved_qty: int | None = None
    grn_ars_reserved_qty: int | None = None
    grn_available_for_first_allocation: int | None = None
    grn_reservations: list[dict] | None = None
    created_at: datetime
    updated_at: datetime


class AllocationSessionDetail(BaseModel):
    session: AllocationSessionOut
    lines: list[AllocationLineOut]


class AllocationLineUpdate(BaseModel):
    final_qty: int
    override_reason: str | None = None
    override_notes: str | None = None


class AllocationSimulateRequest(BaseModel):
    store_id: UUID
    sku_id: UUID
    quantity: int


class AllocationSimulateResponse(BaseModel):
    quantity: int
    weeks_cover: float
    fills_display_capacity: bool
    remaining_capacity_after: int
    projected_sellthrough_eow: float
    stockout_risk: bool
    overstock_risk: bool
    notes: str
