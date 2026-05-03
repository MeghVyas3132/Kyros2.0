from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.routers import (
    admin,
    alerts,
    allocation,
    auth,
    buy_plan,
    clusters,
    grn,
    ingestion,
    onboarding,
    performance,
    seasons,
    skus,
    stores,
)

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


def error_payload(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        },
        "meta": {
            "request_id": "req-local",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(stores.router)
    app.include_router(clusters.router)
    app.include_router(skus.router)
    app.include_router(seasons.router)
    app.include_router(ingestion.router)
    app.include_router(onboarding.router)
    app.include_router(grn.router)
    app.include_router(allocation.router)
    app.include_router(performance.router)
    app.include_router(alerts.router)
    app.include_router(buy_plan.router)
    app.include_router(admin.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            payload = error_payload(detail["code"], detail.get("message", "Request failed"), detail.get("details"))
        else:
            payload = error_payload("VALIDATION_ERROR", str(detail))
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_payload("VALIDATION_ERROR", "Constraint violation", str(exc.orig)),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload("VALIDATION_ERROR", "Request validation failed", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload("INTERNAL_ERROR", "Unexpected server error", str(exc)),
        )

    return app


app = create_app()
