from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backend.contracts.enums import SensorHealth, WorkerStatus
from backend.kafka import ConsumerGroupSnapshot
from backend.operations_service import OperationsHealthService

NOW = datetime(2026, 7, 13, 3, 0, tzinfo=UTC)


class Connection:
    def __init__(self) -> None:
        self.statement = ""

    def execute(self, statement: str, _parameters=None):
        self.statement = statement
        return self

    def fetchone(self):
        if "pg_partition_tree" in self.statement:
            return (0, 0)
        if "dashboard_rollup_coverage" in self.statement:
            return (1440,)
        if "max(source_max_ingested_at)" in self.statement:
            return (NOW - timedelta(seconds=30),)
        return (1,)

    def fetchall(self):
        return []


class HealthyRuntime:
    settings = SimpleNamespace(
        kafka_bootstrap_servers="kafka:9092",
        s3_bucket="edr-failures",
        event_storage_consumer_group="edr-event-storage-v1",
        detection_consumer_group="edr-detection-v1",
        dashboard_rollup_consumer_group="edr-dashboard-rollup-v1",
        dashboard_rollup_freshness_grace_seconds=300,
    )
    producer = SimpleNamespace(check=lambda: None)
    clickhouse = SimpleNamespace(
        command=lambda _statement: 1,
        query=lambda *_args, **_kwargs: SimpleNamespace(result_rows=[(NOW,)]),
    )
    s3 = SimpleNamespace(head_bucket=lambda **_kwargs: {})

    @contextmanager
    def postgres(self):
        yield Connection()


def running_worker(_bootstrap: str, *, group_id: str, topic: str) -> ConsumerGroupSnapshot:
    return ConsumerGroupSnapshot(group_id=group_id, topic=topic, state="STABLE", member_count=1, lag=0)


def test_operations_health_reports_live_services_and_worker_lag() -> None:
    result = OperationsHealthService(HealthyRuntime(), worker_probe=running_worker).snapshot(checked_at=NOW)
    assert result.status is SensorHealth.HEALTHY
    assert [service.service for service in result.services] == [
        "Backend API",
        "PostgreSQL",
        "Event ingest registry capacity",
        "Dashboard rollup coverage",
        "ClickHouse",
        "Kafka",
        "S3",
    ]
    assert all(service.status is SensorHealth.HEALTHY for service in result.services)
    assert all(worker.status is WorkerStatus.RUNNING for worker in result.workers)
    assert [worker.worker for worker in result.workers] == ["Event storage", "Detection", "Dashboard rollup"]
    assert [worker.lag for worker in result.workers] == [0, 0, 0]


def test_operations_health_keeps_partial_results_when_probes_fail() -> None:
    runtime = HealthyRuntime()
    runtime.clickhouse = SimpleNamespace(command=lambda _statement: (_ for _ in ()).throw(RuntimeError("down")))

    def failed_worker(_bootstrap: str, *, group_id: str, topic: str) -> ConsumerGroupSnapshot:
        raise RuntimeError(f"{group_id}:{topic}")

    result = OperationsHealthService(runtime, worker_probe=failed_worker).snapshot(checked_at=NOW)
    assert result.status is SensorHealth.DEGRADED
    clickhouse = next(service for service in result.services if service.service == "ClickHouse")
    assert clickhouse.status is SensorHealth.UNAVAILABLE
    assert "RuntimeError" in clickhouse.detail
    assert all(worker.status is WorkerStatus.UNKNOWN for worker in result.workers)


def test_operations_health_degrades_when_recent_rollup_coverage_has_a_gap() -> None:
    class UncoveredConnection(Connection):
        def fetchone(self):
            return (1439,) if "dashboard_rollup_coverage" in self.statement else (1,)

    class Runtime(HealthyRuntime):
        @contextmanager
        def postgres(self):
            yield UncoveredConnection()

    result = OperationsHealthService(Runtime(), worker_probe=running_worker).snapshot(checked_at=NOW)

    assert result.status is SensorHealth.DEGRADED
    coverage = next(service for service in result.services if service.service == "Dashboard rollup coverage")
    assert coverage.status is SensorHealth.UNAVAILABLE
    assert "RuntimeError" in coverage.detail


def test_operations_health_degrades_when_rollup_watermark_is_stale() -> None:
    class StaleConnection(Connection):
        def fetchone(self):
            if "dashboard_rollup_coverage" in self.statement:
                return (1440,)
            if "max(source_max_ingested_at)" in self.statement:
                return (NOW - timedelta(minutes=10),)
            return (1,)

    class Runtime(HealthyRuntime):
        @contextmanager
        def postgres(self):
            yield StaleConnection()

    result = OperationsHealthService(Runtime(), worker_probe=running_worker).snapshot(checked_at=NOW)

    assert result.status is SensorHealth.DEGRADED
    coverage = next(service for service in result.services if service.service == "Dashboard rollup coverage")
    assert coverage.status is SensorHealth.UNAVAILABLE


def test_operations_health_degrades_before_registry_capacity_is_exhausted() -> None:
    class FullRegistryConnection(Connection):
        def fetchone(self):
            if "pg_partition_tree" in self.statement:
                return (100_000_001, 1024)
            return super().fetchone()

    class Runtime(HealthyRuntime):
        @contextmanager
        def postgres(self):
            yield FullRegistryConnection()

    result = OperationsHealthService(Runtime(), worker_probe=running_worker).snapshot(checked_at=NOW)

    assert result.status is SensorHealth.DEGRADED
    capacity = next(service for service in result.services if service.service == "Event ingest registry capacity")
    assert capacity.status is SensorHealth.UNAVAILABLE
