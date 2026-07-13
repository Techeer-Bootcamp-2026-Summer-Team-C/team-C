from pydantic import SecretStr

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
        agent_ca_cert_path="certs/agent-ca.crt",
        agent_ca_key_path="certs/agent-ca.key",
        _env_file=None,
    )
    assert isinstance(settings.jwt_secret, SecretStr)
    assert settings.model_dump(mode="json")["jwt_secret"] == "**********"
