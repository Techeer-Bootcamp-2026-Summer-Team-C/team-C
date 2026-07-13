from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.contracts.enums import SensorHealth, WorkerStatus
from backend.kafka import ConsumerGroupSnapshot
from backend.operations_service import OperationsHealthService

NOW = datetime(2026, 7, 13, 3, 0, tzinfo=UTC)


class Connection:
    def execute(self, _statement: str):
        return self

    def fetchone(self):
        return (1,)


class HealthyRuntime:
    settings = SimpleNamespace(kafka_bootstrap_servers="kafka:9092", s3_bucket="edr-failures")
    producer = SimpleNamespace(check=lambda: None)
    clickhouse = SimpleNamespace(command=lambda _statement: 1)
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
        "ClickHouse",
        "Kafka",
        "S3",
    ]
    assert all(service.status is SensorHealth.HEALTHY for service in result.services)
    assert all(worker.status is WorkerStatus.RUNNING for worker in result.workers)
    assert [worker.lag for worker in result.workers] == [0, 0]


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
