from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol

from .contracts.enums import SensorHealth, WorkerStatus
from .contracts.operations import OperationsHealthDto, PipelineWorkerDto, ServiceHealthDto
from .kafka import RAW_TOPIC, VALIDATED_TOPIC, ConsumerGroupSnapshot, consumer_group_snapshot

WORKERS = (
    ("Event storage", "edr-event-storage-v1", RAW_TOPIC),
    ("Detection", "edr-detection-v1", VALIDATED_TOPIC),
)


class OperationsRuntime(Protocol):
    settings: Any
    producer: Any
    clickhouse: Any
    s3: Any

    def postgres(self) -> AbstractContextManager[Any]: ...


WorkerProbe = Callable[..., ConsumerGroupSnapshot]


class OperationsHealthService:
    def __init__(
        self,
        runtime: OperationsRuntime,
        *,
        worker_probe: WorkerProbe = consumer_group_snapshot,
    ) -> None:
        self.runtime = runtime
        self.worker_probe = worker_probe

    def snapshot(self, *, checked_at: datetime | None = None) -> OperationsHealthDto:
        checked_at = (checked_at or datetime.now(UTC)).astimezone(UTC)
        services = [
            ServiceHealthDto(
                service="Backend API",
                status=SensorHealth.HEALTHY,
                latency_ms=0,
                detail="The authenticated operations endpoint is responding.",
            ),
            self._probe("PostgreSQL", self._check_postgres),
            self._probe("ClickHouse", lambda: self.runtime.clickhouse.command("SELECT 1")),
            self._probe("Kafka", self.runtime.producer.check),
            self._probe("S3", lambda: self.runtime.s3.head_bucket(Bucket=self.runtime.settings.s3_bucket)),
        ]
        workers = [self._worker(worker, group_id, topic) for worker, group_id, topic in WORKERS]
        degraded = any(item.status is not SensorHealth.HEALTHY for item in services) or any(
            item.status is not WorkerStatus.RUNNING for item in workers
        )
        return OperationsHealthDto(
            checked_at=checked_at,
            status=SensorHealth.DEGRADED if degraded else SensorHealth.HEALTHY,
            services=services,
            workers=workers,
        )

    def _check_postgres(self) -> None:
        with self.runtime.postgres() as connection:
            connection.execute("SELECT 1").fetchone()

    @staticmethod
    def _status(snapshot: ConsumerGroupSnapshot) -> WorkerStatus:
        if snapshot.member_count is None:
            return WorkerStatus.UNKNOWN
        if snapshot.member_count > 0:
            return WorkerStatus.RUNNING
        return WorkerStatus.OFFLINE if snapshot.lag > 0 else WorkerStatus.IDLE

    def _worker(self, worker: str, group_id: str, topic: str) -> PipelineWorkerDto:
        try:
            snapshot = self.worker_probe(
                self.runtime.settings.kafka_bootstrap_servers,
                group_id=group_id,
                topic=topic,
            )
            return PipelineWorkerDto(
                worker=worker,
                group_id=group_id,
                topic=topic,
                status=self._status(snapshot),
                member_count=snapshot.member_count,
                lag=snapshot.lag,
                detail=f"Broker group state {snapshot.state}.",
            )
        except Exception as error:
            return PipelineWorkerDto(
                worker=worker,
                group_id=group_id,
                topic=topic,
                status=WorkerStatus.UNKNOWN,
                member_count=None,
                lag=None,
                detail=f"Worker probe failed ({type(error).__name__}).",
            )

    @staticmethod
    def _probe(service: str, check: Callable[[], Any]) -> ServiceHealthDto:
        started = perf_counter()
        try:
            check()
            status = SensorHealth.HEALTHY
            detail = "Live dependency probe succeeded."
        except Exception as error:
            status = SensorHealth.UNAVAILABLE
            detail = f"Live dependency probe failed ({type(error).__name__})."
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        return ServiceHealthDto(service=service, status=status, latency_ms=latency_ms, detail=detail)
