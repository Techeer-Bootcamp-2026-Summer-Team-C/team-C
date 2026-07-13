from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
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
    postgres_dsn: SecretStr
    clickhouse_dsn: SecretStr
    kafka_bootstrap_servers: str
    s3_endpoint_url: str
    s3_access_key_id: SecretStr
    s3_secret_access_key: SecretStr
    s3_bucket: str = "edr-failures"
    agent_ca_cert_path: Path
    agent_ca_key_path: Path


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
