from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import AlertType


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    alert_type: AlertType
    severity: str
    title: str
    message: str
    store_id: UUID | None
    sku_id: UUID | None
    grn_id: UUID | None
    season_id: UUID | None
    action_url: str | None
    is_read: bool
    is_dismissed: bool
    generated_at: datetime
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AlertCount(BaseModel):
    unread: int
    high: int
    medium: int
    low: int
