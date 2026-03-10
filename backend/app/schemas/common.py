from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Meta(BaseModel):
    request_id: str = "req-local"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Envelope(BaseModel):
    data: Any
    meta: Meta = Field(default_factory=Meta)


class ErrorDetail(BaseModel):
    row: int | None = None
    field: str | None = None
    value: Any | None = None
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    meta: Meta = Field(default_factory=Meta)
