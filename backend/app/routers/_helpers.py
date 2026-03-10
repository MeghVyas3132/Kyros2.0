from datetime import UTC, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder


def envelope(data: Any) -> dict[str, Any]:
    return {
        "data": jsonable_encoder(data),
        "meta": {
            "request_id": "req-local",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }


def error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return {
        "error": payload,
        "meta": {
            "request_id": "req-local",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }
