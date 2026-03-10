from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StylePerformanceOut(BaseModel):
    sku_id: UUID
    style_code: str
    style_name: str
    category: str
    ros_7d: float | None
    sell_through_pct: float | None
    stock_cover_days: float | None
    units_on_hand: int
    days_since_grn: int | None
    style_status: str | None
    stores_exposed: int
    stores_stockout: int


class StorePerformanceOut(BaseModel):
    store_id: UUID
    store_name: str
    avg_sell_through_pct: float | None
    avg_ros: float | None
    avg_stock_cover_days: float | None
    styles_exposed: int
    styles_healthy: int
    styles_watch: int
    styles_problem: int
    styles_critical: int
    styles_stockout: int


class PerformanceSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    snapshot_date: date
    season_id: UUID | None
    store_id: UUID
    sku_id: UUID
    units_sold_today: int
    units_sold_7d: int
    units_sold_28d: int
    units_on_hand: int
    sell_through_pct: float | None
    ros_7d: float | None
    stock_cover_days: float | None
    days_since_grn: int | None
    style_status: str | None
    is_stockout: bool
    lost_sales_estimate: float | None
    created_at: datetime
    updated_at: datetime
