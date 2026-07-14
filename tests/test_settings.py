import pytest
from pydantic import SecretStr, ValidationError

from backend.settings import Settings


def base_settings(**overrides):
    values = {
        "jwt_secret": "jwt-secret",
        "postgres_dsn": "postgresql://user:password@localhost/edr",
        "clickhouse_dsn": "http://user:password@localhost:8123/edr",
        "kafka_bootstrap_servers": "localhost:9092",
        "_env_file": None,
    }
    values.update(overrides)
    return values


def test_secrets_are_injected_and_masked() -> None:
    settings = Settings(
        jwt_secret="jwt-secret",
        postgres_dsn="postgresql://user:password@localhost/edr",
        clickhouse_dsn="http://user:password@localhost:8123/edr",
        kafka_bootstrap_servers="localhost:9092",
        s3_endpoint_url="http://localhost:9000",
        s3_access_key_id="access-key",
        s3_secret_access_key="secret-key",
        _env_file=None,
    )
    assert isinstance(settings.jwt_secret, SecretStr)
    assert settings.model_dump(mode="json")["jwt_secret"] == "**********"
    assert settings.access_token_ttl_seconds == 43_200


def test_minio_endpoint_and_explicit_credentials_are_valid() -> None:
    settings = Settings(
        **base_settings(
            aws_region="us-east-1",
            s3_endpoint_url="http://localhost:9000",
            s3_access_key_id="access-key",
            s3_secret_access_key="secret-key",
        )
    )

    assert settings.s3_endpoint_url == "http://localhost:9000"
    assert settings.s3_access_key_id is not None
    assert settings.s3_secret_access_key is not None


def test_aws_iam_role_mode_needs_no_endpoint_or_explicit_credentials() -> None:
    settings = Settings(
        **base_settings(
            env="production",
            jwt_secret="production-jwt-secret-with-at-least-32-characters",
            aws_region="ap-northeast-2",
            s3_bucket="production-bucket",
        )
    )

    assert settings.aws_region == "ap-northeast-2"
    assert settings.s3_endpoint_url is None
    assert settings.s3_access_key_id is None
    assert settings.s3_secret_access_key is None


def test_aws_iam_role_mode_loads_from_prefixed_environment(monkeypatch) -> None:
    monkeypatch.setenv("EDR_ENV", "production")
    monkeypatch.setenv("EDR_JWT_SECRET", "production-jwt-secret-with-at-least-32-characters")
    monkeypatch.setenv("EDR_POSTGRES_DSN", "postgresql://user:password@localhost/edr")
    monkeypatch.setenv("EDR_CLICKHOUSE_DSN", "http://user:password@localhost:8123/edr")
    monkeypatch.setenv("EDR_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("EDR_AWS_REGION", "ap-northeast-2")
    monkeypatch.setenv("EDR_S3_BUCKET", "production-bucket")
    monkeypatch.delenv("EDR_S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("EDR_S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("EDR_S3_SECRET_ACCESS_KEY", raising=False)

    settings = Settings(_env_file=None)

    assert settings.aws_region == "ap-northeast-2"
    assert settings.s3_bucket == "production-bucket"
    assert settings.s3_endpoint_url is None
    assert settings.s3_access_key_id is None
    assert settings.s3_secret_access_key is None


def test_local_environment_keeps_the_default_s3_bucket() -> None:
    settings = Settings(**base_settings())

    assert settings.s3_bucket == "edr-failures"


@pytest.mark.parametrize("bucket", [None, "", "   ", "None"])
def test_non_local_environment_requires_an_explicit_s3_bucket(bucket: str | None) -> None:
    values = base_settings(
        env="production",
        jwt_secret="production-jwt-secret-with-at-least-32-characters",
        aws_region="ap-northeast-2",
    )
    if bucket is not None:
        values["s3_bucket"] = bucket

    with pytest.raises(ValidationError, match="EDR_S3_BUCKET is required outside local"):
        Settings(**values)


@pytest.mark.parametrize("bucket", ["", "   ", "None"])
def test_local_blank_s3_bucket_values_fall_back_to_the_local_default(bucket: str) -> None:
    settings = Settings(**base_settings(s3_bucket=bucket))

    assert settings.s3_bucket == "edr-failures"


@pytest.mark.parametrize(
    ("access_key", "secret_key"),
    [("access-key", None), (None, "secret-key")],
)
def test_s3_credentials_must_be_configured_as_a_pair(access_key: str | None, secret_key: str | None) -> None:
    with pytest.raises(ValidationError, match="must be set together"):
        Settings(
            **base_settings(
                s3_access_key_id=access_key,
                s3_secret_access_key=secret_key,
            )
        )


def test_blank_optional_s3_values_are_normalized_to_none() -> None:
    settings = Settings(
        **base_settings(
            s3_endpoint_url="  ",
            s3_access_key_id="",
            s3_secret_access_key="None",
        )
    )

    assert settings.s3_endpoint_url is None
    assert settings.s3_access_key_id is None
    assert settings.s3_secret_access_key is None


def test_kafka_defaults_match_the_two_worker_pipeline() -> None:
    settings = Settings(**base_settings())

    assert settings.kafka_topics == ("telemetry.raw", "telemetry.validated")
    assert settings.kafka_partitions_per_topic == 2
    assert settings.kafka_replication_factor == 1
    assert settings.event_storage_consumer_group == "edr-event-storage-v1"
    assert settings.detection_consumer_group == "edr-detection-v1"


@pytest.mark.parametrize(
    ("field", "value"),
    [("kafka_partitions_per_topic", 0), ("kafka_replication_factor", 0)],
)
def test_kafka_counts_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**base_settings(**{field: value}))


@pytest.mark.parametrize("ttl", [299, 604_801])
def test_access_token_ttl_is_bounded(ttl: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            jwt_secret="jwt-secret",
            access_token_ttl_seconds=ttl,
            postgres_dsn="postgresql://user:password@localhost/edr",
            clickhouse_dsn="http://user:password@localhost:8123/edr",
            kafka_bootstrap_servers="localhost:9092",
            s3_endpoint_url="http://localhost:9000",
            s3_access_key_id="access-key",
            s3_secret_access_key="secret-key",
            _env_file=None,
        )


@pytest.mark.parametrize("jwt_secret", ["short", "replace-with-a-long-random-secret"])
def test_non_local_environment_rejects_weak_or_placeholder_jwt_secret(jwt_secret: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            env="production",
            aws_region="ap-northeast-2",
            jwt_secret=jwt_secret,
            postgres_dsn="postgresql://user:password@localhost/edr",
            clickhouse_dsn="http://user:password@localhost:8123/edr",
            kafka_bootstrap_servers="localhost:9092",
            s3_endpoint_url="http://localhost:9000",
            s3_access_key_id="access-key",
            s3_secret_access_key="secret-key",
            s3_bucket="production-bucket",
            _env_file=None,
        )


def test_non_local_environment_accepts_a_strong_jwt_secret() -> None:
    settings = Settings(
        env="production",
        aws_region="ap-northeast-2",
        jwt_secret="production-jwt-secret-with-at-least-32-characters",
        postgres_dsn="postgresql://user:password@localhost/edr",
        clickhouse_dsn="http://user:password@localhost:8123/edr",
        kafka_bootstrap_servers="localhost:9092",
        s3_endpoint_url="http://localhost:9000",
        s3_access_key_id="access-key",
        s3_secret_access_key="secret-key",
        s3_bucket="production-bucket",
        _env_file=None,
    )
    assert settings.env == "production"
