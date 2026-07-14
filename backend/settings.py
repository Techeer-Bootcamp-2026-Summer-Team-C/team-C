from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_S3_BUCKET_DEFAULT = "edr-failures"


class Settings(BaseSettings):
    """Environment-only runtime configuration; secrets are never serialized."""

    model_config = SettingsConfigDict(
        env_prefix="EDR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    env: str = "local"
    log_level: str = "INFO"
    jwt_secret: SecretStr
    access_token_ttl_seconds: int = Field(default=43_200, ge=300, le=604_800)
    postgres_dsn: SecretStr
    clickhouse_dsn: SecretStr
    kafka_bootstrap_servers: str
    kafka_raw_topic: str = "telemetry.raw"
    kafka_validated_topic: str = "telemetry.validated"
    kafka_partitions_per_topic: int = Field(default=2, ge=1)
    kafka_replication_factor: int = Field(default=1, ge=1)
    event_storage_consumer_group: str = "edr-event-storage-v1"
    detection_consumer_group: str = "edr-detection-v1"
    aws_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_bucket: str | None = LOCAL_S3_BUCKET_DEFAULT

    @field_validator(
        "aws_region",
        "s3_endpoint_url",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_bucket",
        mode="before",
    )
    @classmethod
    def normalize_optional_s3_value(cls, value: object) -> object | None:
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized or normalized.lower() == "none":
                return None
            return normalized
        return value

    @model_validator(mode="after")
    def validate_runtime_configuration(self) -> Self:
        has_access_key = self.s3_access_key_id is not None
        has_secret_key = self.s3_secret_access_key is not None
        if has_access_key != has_secret_key:
            raise ValueError("EDR_S3_ACCESS_KEY_ID and EDR_S3_SECRET_ACCESS_KEY must be set together or both omitted")
        if self.env.lower() != "local" and self.aws_region is None:
            raise ValueError("EDR_AWS_REGION is required outside local")
        if self.env.lower() != "local" and (
            self.s3_bucket is None or "s3_bucket" not in self.model_fields_set
        ):
            raise ValueError("EDR_S3_BUCKET is required outside local")
        if self.env.lower() == "local" and self.s3_bucket is None:
            self.s3_bucket = LOCAL_S3_BUCKET_DEFAULT
        if self.kafka_raw_topic == self.kafka_validated_topic:
            raise ValueError("EDR_KAFKA_RAW_TOPIC and EDR_KAFKA_VALIDATED_TOPIC must be different")
        return self

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

    @property
    def kafka_topics(self) -> tuple[str, str]:
        return self.kafka_raw_topic, self.kafka_validated_topic


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
