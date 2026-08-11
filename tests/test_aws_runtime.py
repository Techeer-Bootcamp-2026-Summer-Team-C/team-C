from threading import BoundedSemaphore
from types import SimpleNamespace

import pytest

import backend.event_service as event_service_module
import backend.runtime as runtime_module
from backend.errors import ServiceUnavailableError
from backend.event_service import RestoredEventReader
from backend.runtime import RuntimeServices, clickhouse_dsn_for_role, create_s3_client
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
    config = captured["options"].pop("config")
    assert captured == {
        "service": "s3",
        "options": {"region_name": "ap-northeast-2"},
    }
    assert config.connect_timeout == 5
    assert config.read_timeout == 10


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

    config = captured["options"].pop("config")
    assert captured == {
        "service": "s3",
        "options": {
            "region_name": "us-east-1",
            "endpoint_url": "http://minio:9000",
            "aws_access_key_id": "minio-access",
            "aws_secret_access_key": "minio-secret",
        },
    }
    assert config.connect_timeout == 5
    assert config.read_timeout == 10


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

    assert captured == {"region": "ap-northeast-2", "connect_timeout": 5, "request_timeout": 10}


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
        "connect_timeout": 5,
        "request_timeout": 10,
    }


def test_dashboard_live_query_guard_rejects_excess_concurrency_and_releases_slot() -> None:
    runtime = object.__new__(RuntimeServices)
    runtime._dashboard_live_slots = BoundedSemaphore(1)

    with runtime.dashboard_live_query_guard():
        with pytest.raises(ServiceUnavailableError, match="capacity is exhausted"):
            with runtime.dashboard_live_query_guard():
                pass

    with runtime.dashboard_live_query_guard():
        pass


def test_dashboard_live_query_guard_uses_postgres_slots_across_processes() -> None:
    class Result:
        def __init__(self, value: bool) -> None:
            self.value = value

        def fetchone(self):
            return (self.value,)

    class Connection:
        def __init__(self, available: list[bool]) -> None:
            self.available = iter(available)
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, statement, parameters):
            self.calls.append((statement, parameters))
            if "pg_try_advisory_lock" in statement:
                return Result(next(self.available))
            return Result(True)

    runtime = object.__new__(RuntimeServices)
    runtime.settings = SimpleNamespace(dashboard_live_max_concurrency=2)
    runtime._dashboard_live_slots = BoundedSemaphore(2)
    connection = Connection([False, True])

    with runtime.dashboard_live_query_guard(connection):
        pass

    assert connection.calls[0][1][1] == 0
    assert connection.calls[1][1][1] == 1
    assert "pg_advisory_unlock" in connection.calls[-1][0]

    with pytest.raises(ServiceUnavailableError, match="capacity is exhausted"):
        with runtime.dashboard_live_query_guard(Connection([False, False])):
            pass


def test_clickhouse_runtime_roles_use_separate_credentials_with_safe_fallback() -> None:
    configured = settings(
        clickhouse_read_dsn="http://read@clickhouse/edr",
        clickhouse_worker_dsn="http://worker@clickhouse/edr",
        clickhouse_lifecycle_dsn="http://lifecycle@clickhouse/edr",
    )

    assert clickhouse_dsn_for_role(configured, "read") == "http://read@clickhouse/edr"
    assert clickhouse_dsn_for_role(configured, "worker") == "http://worker@clickhouse/edr"
    assert clickhouse_dsn_for_role(configured, "lifecycle") == "http://lifecycle@clickhouse/edr"
    assert clickhouse_dsn_for_role(settings(), "read") == "http://user:password@localhost:8123/edr"
