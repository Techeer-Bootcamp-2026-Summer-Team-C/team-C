from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-only runtime configuration; secrets are never serialized."""

    model_config = SettingsConfigDict(
        env_prefix="EDR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    log_level: str = "INFO"
    jwt_secret: SecretStr
    access_token_ttl_seconds: int = Field(default=43_200, ge=300, le=604_800)
    postgres_dsn: SecretStr
    clickhouse_dsn: SecretStr
    kafka_bootstrap_servers: str
    s3_endpoint_url: str
    s3_access_key_id: SecretStr
    s3_secret_access_key: SecretStr
    s3_bucket: str = "edr-failures"

    @model_validator(mode="after")
    def require_production_jwt_secret(self) -> Self:
        if self.env.lower() == "local":
            return self
        secret = self.jwt_secret.get_secret_value()
        placeholders = {
            "local-dev-only-change-before-deployment",
            "replace-with-a-long-random-secret",
        }
        if len(secret) < 32 or secret in placeholders:
            raise ValueError("EDR_JWT_SECRET must be a non-placeholder value of at least 32 characters outside local")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
