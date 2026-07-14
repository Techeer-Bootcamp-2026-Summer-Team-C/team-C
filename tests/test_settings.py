import pytest
from pydantic import SecretStr, ValidationError

from backend.settings import Settings


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
            jwt_secret=jwt_secret,
            postgres_dsn="postgresql://user:password@localhost/edr",
            clickhouse_dsn="http://user:password@localhost:8123/edr",
            kafka_bootstrap_servers="localhost:9092",
            s3_endpoint_url="http://localhost:9000",
            s3_access_key_id="access-key",
            s3_secret_access_key="secret-key",
            _env_file=None,
        )


def test_non_local_environment_accepts_a_strong_jwt_secret() -> None:
    settings = Settings(
        env="production",
        jwt_secret="production-jwt-secret-with-at-least-32-characters",
        postgres_dsn="postgresql://user:password@localhost/edr",
        clickhouse_dsn="http://user:password@localhost:8123/edr",
        kafka_bootstrap_servers="localhost:9092",
        s3_endpoint_url="http://localhost:9000",
        s3_access_key_id="access-key",
        s3_secret_access_key="secret-key",
        _env_file=None,
    )
    assert settings.env == "production"
