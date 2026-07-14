import backend.event_service as event_service_module
import backend.runtime as runtime_module
from backend.event_service import RestoredEventReader
from backend.runtime import create_s3_client
from backend.settings import Settings


def settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "jwt-secret",
        "postgres_dsn": "postgresql://user:password@localhost/edr",
        "clickhouse_dsn": "http://user:password@localhost:8123/edr",
        "kafka_bootstrap_servers": "localhost:9092",
        "aws_region": "ap-northeast-2",
        "s3_bucket": "bucket",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_boto3_aws_mode_uses_region_without_endpoint_or_explicit_credentials(monkeypatch) -> None:
    captured = {}
    sentinel = object()

    def fake_client(service: str, **options):
        captured["service"] = service
        captured["options"] = options
        return sentinel

    monkeypatch.setattr(runtime_module.boto3, "client", fake_client)

    assert create_s3_client(settings()) is sentinel
    assert captured == {
        "service": "s3",
        "options": {"region_name": "ap-northeast-2"},
    }


def test_boto3_minio_mode_passes_endpoint_region_and_explicit_credentials(monkeypatch) -> None:
    captured = {}

    def fake_client(service: str, **options):
        captured["service"] = service
        captured["options"] = options
        return object()

    monkeypatch.setattr(runtime_module.boto3, "client", fake_client)
    create_s3_client(
        settings(
            aws_region="us-east-1",
            s3_endpoint_url="http://minio:9000",
            s3_access_key_id="minio-access",
            s3_secret_access_key="minio-secret",
        )
    )

    assert captured == {
        "service": "s3",
        "options": {
            "region_name": "us-east-1",
            "endpoint_url": "http://minio:9000",
            "aws_access_key_id": "minio-access",
            "aws_secret_access_key": "minio-secret",
        },
    }


def test_pyarrow_aws_mode_uses_region_without_endpoint_or_explicit_credentials(monkeypatch) -> None:
    captured = {}

    def fake_filesystem(**options):
        captured.update(options)
        return object()

    monkeypatch.setattr(event_service_module.pafs, "S3FileSystem", fake_filesystem)

    RestoredEventReader(
        region="ap-northeast-2",
        endpoint_url=None,
        access_key=None,
        secret_key=None,
        bucket="bucket",
    )

    assert captured == {"region": "ap-northeast-2"}


def test_pyarrow_minio_mode_passes_endpoint_and_explicit_credentials(monkeypatch) -> None:
    captured = {}

    def fake_filesystem(**options):
        captured.update(options)
        return object()

    monkeypatch.setattr(event_service_module.pafs, "S3FileSystem", fake_filesystem)

    RestoredEventReader(
        region="us-east-1",
        endpoint_url="http://minio:9000",
        access_key="minio-access",
        secret_key="minio-secret",
        bucket="bucket",
    )

    assert captured == {
        "region": "us-east-1",
        "endpoint_override": "minio:9000",
        "scheme": "http",
        "access_key": "minio-access",
        "secret_key": "minio-secret",
    }
