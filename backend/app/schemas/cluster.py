from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ClusterBase(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True


class ClusterCreate(ClusterBase):
    pass


class ClusterUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class ClusterOut(ClusterBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    created_at: datetime
    updated_at: datetime
