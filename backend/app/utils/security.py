from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.models import User

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
settings = get_settings()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(user: User) -> str:
    expire = datetime.now(UTC) + timedelta(hours=settings.jwt_access_token_expire_hours)
    payload = {
        "sub": str(user.id),
        "brand_id": str(user.brand_id),
        "role": user.role.value,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user: User) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": str(user.id),
        "brand_id": str(user.brand_id),
        "role": user.role.value,
        "token_type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def parse_uuid(value: str) -> UUID:
    return UUID(value)


class TokenError(Exception):
    pass


def validate_access_token(token: str) -> dict[str, Any]:
    try:
        payload = decode_token(token)
        if payload.get("token_type") == "refresh":
            raise TokenError("AUTH_INVALID")
        return payload
    except JWTError as exc:
        raise TokenError("AUTH_INVALID") from exc


def validate_refresh_token(token: str) -> dict[str, Any]:
    try:
        payload = decode_token(token)
        if payload.get("token_type") != "refresh":
            raise TokenError("AUTH_INVALID")
        return payload
    except JWTError as exc:
        raise TokenError("AUTH_INVALID") from exc
