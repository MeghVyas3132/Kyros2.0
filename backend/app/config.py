from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Kyros API"
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    database_url: str = Field(
        default="postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    jwt_secret_key: str = Field(
        default="dev-secret-key-change-in-production-minimum-32-chars", alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_hours: int = Field(default=8, alias="JWT_ACCESS_TOKEN_EXPIRE_HOURS")
    jwt_refresh_token_expire_days: int = Field(default=30, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    s3_bucket_name: str = Field(default="kyros-uploads-local", alias="S3_BUCKET_NAME")
    local_storage: bool = Field(default=True, alias="LOCAL_STORAGE")
    local_storage_path: str = Field(default="/tmp/kyros_uploads", alias="LOCAL_STORAGE_PATH")

    celery_broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
