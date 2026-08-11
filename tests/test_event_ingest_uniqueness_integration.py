import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID

import clickhouse_connect
import psycopg
import pytest

from backend.contracts.enums import OsType
from backend.kafka import RAW_TOPIC, ConsumedMessage
from backend.storage.clickhouse import EventRepository
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_migrations
from backend.storage.models import EndpointInsert
from backend.storage.postgres import (
    EndpointRepository,
    EventIngestRegistryRepository,
    IngestMetadataRepository,
)
from backend.workers import EventStorageWorker, normalize_event
from tools.audit_event_duplicates import audit_event_duplicates

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
EVENT_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3f001")
LEGACY_EVENT_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3f002")
AMBIGUOUS_EVENT_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3f003")
PUBLISH_RETRY_EVENT_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3f004")
LEGACY_DUPLICATE_EVENT_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3f005")
LEGACY_CONFLICT_EVENT_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3f006")
RUN_INTEGRATION = os.getenv("EDR_RUN_STORAGE_INTEGRATION") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not RUN_INTEGRATION, reason="event uniqueness integration disabled"),
]


class OneMessageConsumer:
    def __init__(self, message: ConsumedMessage) -> None:
        self.message = message
        self.committed: list[int] = []
        self.rewound: list[int] = []

    def consume_one(self, _timeout: float) -> ConsumedMessage | None:
        message, self.message = self.message, None
        return message

    def commit(self, message: ConsumedMessage) -> None:
        self.committed.append(message.offset)

    def rewind(self, message: ConsumedMessage) -> None:
        self.rewound.append(message.offset)


class CapturingProducer:
    def __init__(self) -> None:
        self.messages: list[bytes] = []

    def publish(self, _topic: str, *, key: str, value: bytes, headers=None) -> bool:
        assert key
        assert headers is None
        self.messages.append(value)
        return True


class SequencedProducer(CapturingProducer):
    def __init__(self, acknowledgements: list[bool]) -> None:
        super().__init__()
        self.acknowledgements = acknowledgements

    def publish(self, topic: str, *, key: str, value: bytes, headers=None) -> bool:
        super().publish(topic, key=key, value=value, headers=headers)
        return self.acknowledgements.pop(0)


class CapturingFailureSink:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(self, _message: ConsumedMessage, **kwargs):
        self.records.append(kwargs)


class RollbackAfterClaimRegistry:
    """Simulate losing the PostgreSQL commit after ClickHouse accepted the event."""

    def __init__(self, connection) -> None:
        self.repository = EventIngestRegistryRepository(connection)

    @contextmanager
    def claim(self, **kwargs):
        with self.repository.claim(**kwargs) as claim:
            yield claim
            raise RuntimeError("simulated registry commit failure")


def _raw_message(endpoint_id: int, *, event_id: UUID, offset: int, command_line: str) -> ConsumedMessage:
    value = json.dumps(
        {
            "schemaVersion": 1,
            "batchId": f"018ff8f4-86de-7b25-9b8a-2d22f6a3e{offset:03d}",
            "endpointId": endpoint_id,
            "agentId": "agent-unique-001",
            "hostname": "UNIQUE-ENDPOINT",
            "osType": "WINDOWS",
            "ipAddress": None,
            "event": {
                "eventId": str(event_id),
                "eventType": "PROCESS_EXECUTION",
                "occurredAt": "2026-07-12T00:59:59Z",
                "payload": {
                    "processName": "powershell.exe",
                    "pid": 42,
                    "commandLine": command_line,
                },
            },
        },
        separators=(",", ":"),
    ).encode()
    return ConsumedMessage(RAW_TOPIC, 0, offset, str(endpoint_id).encode(), value, [])


def _clickhouse_client():
    return clickhouse_connect.get_client(
        host=os.getenv("TEST_CLICKHOUSE_HOST", "127.0.0.1"),
        port=int(os.getenv("TEST_CLICKHOUSE_PORT", "58123")),
        username=os.getenv("TEST_CLICKHOUSE_USER", "edr"),
        password=os.environ["TEST_CLICKHOUSE_PASSWORD"],
        database=os.getenv("TEST_CLICKHOUSE_DATABASE", "edr"),
    )


def test_event_id_primary_key_serializes_clickhouse_storage_and_recovers_legacy_rows() -> None:
    postgres_dsn = os.environ["TEST_POSTGRES_DSN"]
    postgres_migrations = ROOT / "migrations/postgresql"
    clickhouse_down = ROOT / "migrations/clickhouse/0001_initial.down.sql"
    clickhouse_up = ROOT / "migrations/clickhouse/0001_initial.up.sql"
    clickhouse = _clickhouse_client()

    with psycopg.connect(postgres_dsn) as connection:
        apply_postgres_migrations(connection, postgres_migrations, direction="down")
        apply_postgres_migrations(connection, postgres_migrations)
        endpoint_id = EndpointRepository(connection).insert(
            EndpointInsert("agent-unique-001", "UNIQUE-ENDPOINT", OsType.WINDOWS, NOW)
        )
    apply_clickhouse_file(clickhouse, clickhouse_down)
    apply_clickhouse_file(clickhouse, clickhouse_up)
    clickhouse.command("SYSTEM STOP MERGES edr_events")

    try:
        start_together = Barrier(2)

        def store_concurrently(offset: int) -> tuple[list[int], int, int]:
            consumer = OneMessageConsumer(
                _raw_message(
                    endpoint_id,
                    event_id=EVENT_ID,
                    offset=offset,
                    command_line="powershell.exe -EncodedCommand ZQBjAGgAbwA=",
                )
            )
            producer = CapturingProducer()
            failure_sink = CapturingFailureSink()
            worker_clickhouse = _clickhouse_client()
            try:
                with psycopg.connect(postgres_dsn) as connection:
                    worker = EventStorageWorker(
                        consumer=consumer,
                        producer=producer,
                        events=EventRepository.for_ingest(worker_clickhouse),
                        registry=EventIngestRegistryRepository(connection),
                        metadata=IngestMetadataRepository(connection),
                        failure_sink=failure_sink,
                        sleep=lambda _delay: None,
                        now=lambda: NOW,
                    )
                    start_together.wait(timeout=10)
                    assert worker.run_once() is True
            finally:
                worker_clickhouse.close()
            return consumer.committed, len(producer.messages), len(failure_sink.records)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(store_concurrently, offset) for offset in (1, 2)]
            concurrent_results = [future.result(timeout=20) for future in futures]

        assert concurrent_results == [([1], 1, 0), ([2], 1, 0)]
        assert clickhouse.query(
            "SELECT count(), uniqExact(event_id) FROM edr_events WHERE event_id = {event_id:UUID}",
            parameters={"event_id": str(EVENT_ID)},
        ).result_rows == [(1, 1)]
        with psycopg.connect(postgres_dsn) as connection:
            assert connection.execute(
                "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                (EVENT_ID,),
            ).fetchone()[0] == 1

            conflict_consumer = OneMessageConsumer(
                _raw_message(
                    endpoint_id,
                    event_id=EVENT_ID,
                    offset=3,
                    command_line="different payload",
                )
            )
            conflict_producer = CapturingProducer()
            conflict_sink = CapturingFailureSink()
            conflict_worker = EventStorageWorker(
                consumer=conflict_consumer,
                producer=conflict_producer,
                events=EventRepository.for_ingest(clickhouse),
                registry=EventIngestRegistryRepository(connection),
                metadata=IngestMetadataRepository(connection),
                failure_sink=conflict_sink,
                sleep=lambda _delay: None,
                now=lambda: NOW,
            )
            assert conflict_worker.run_once() is True
            assert conflict_consumer.committed == [3]
            assert conflict_producer.messages == []
            assert conflict_sink.records[0]["failure_code"] == "EVENT_IDENTITY_CONFLICT"

        assert clickhouse.query(
            "SELECT count() FROM edr_events WHERE event_id = {event_id:UUID}",
            parameters={"event_id": str(EVENT_ID)},
        ).result_rows == [(1,)]

        legacy_message = _raw_message(
            endpoint_id,
            event_id=LEGACY_EVENT_ID,
            offset=4,
            command_line="legacy event",
        )
        legacy_record = normalize_event(json.loads(legacy_message.value), ingested_at=NOW)
        EventRepository.for_maintenance(clickhouse).insert([legacy_record])
        with psycopg.connect(postgres_dsn) as connection:
            legacy_consumer = OneMessageConsumer(legacy_message)
            legacy_worker = EventStorageWorker(
                consumer=legacy_consumer,
                producer=CapturingProducer(),
                events=EventRepository.for_ingest(clickhouse),
                registry=EventIngestRegistryRepository(connection),
                metadata=IngestMetadataRepository(connection),
                failure_sink=CapturingFailureSink(),
                sleep=lambda _delay: None,
                now=lambda: NOW,
            )
            assert legacy_worker.run_once() is True
            assert connection.execute(
                "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                (LEGACY_EVENT_ID,),
            ).fetchone()[0] == 1
        assert clickhouse.query(
            "SELECT count() FROM edr_events WHERE event_id = {event_id:UUID}",
            parameters={"event_id": str(LEGACY_EVENT_ID)},
        ).result_rows == [(1,)]

        ambiguous_message = _raw_message(
            endpoint_id,
            event_id=AMBIGUOUS_EVENT_ID,
            offset=5,
            command_line="commit window event",
        )
        with psycopg.connect(postgres_dsn) as connection:
            ambiguous_consumer = OneMessageConsumer(ambiguous_message)
            ambiguous_sink = CapturingFailureSink()
            ambiguous_worker = EventStorageWorker(
                consumer=ambiguous_consumer,
                producer=CapturingProducer(),
                events=EventRepository.for_ingest(clickhouse),
                registry=RollbackAfterClaimRegistry(connection),
                metadata=IngestMetadataRepository(connection),
                failure_sink=ambiguous_sink,
                sleep=lambda _delay: None,
                now=lambda: NOW,
            )
            assert ambiguous_worker.run_once() is True
            assert ambiguous_worker.reset_requested is True
            assert ambiguous_consumer.committed == [5]
            assert ambiguous_sink.records[0]["retryable"] is True
            assert connection.execute(
                "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                (AMBIGUOUS_EVENT_ID,),
            ).fetchone()[0] == 0
        assert clickhouse.query(
            "SELECT count() FROM edr_events WHERE event_id = {event_id:UUID}",
            parameters={"event_id": str(AMBIGUOUS_EVENT_ID)},
        ).result_rows == [(1,)]

        with psycopg.connect(postgres_dsn) as connection:
            recovery_consumer = OneMessageConsumer(
                _raw_message(
                    endpoint_id,
                    event_id=AMBIGUOUS_EVENT_ID,
                    offset=6,
                    command_line="commit window event",
                )
            )
            recovery_worker = EventStorageWorker(
                consumer=recovery_consumer,
                producer=CapturingProducer(),
                events=EventRepository.for_ingest(clickhouse),
                registry=EventIngestRegistryRepository(connection),
                metadata=IngestMetadataRepository(connection),
                failure_sink=CapturingFailureSink(),
                sleep=lambda _delay: None,
                now=lambda: NOW,
            )
            assert recovery_worker.run_once() is True
            assert connection.execute(
                "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                (AMBIGUOUS_EVENT_ID,),
            ).fetchone()[0] == 1
        assert clickhouse.query(
            "SELECT count() FROM edr_events WHERE event_id = {event_id:UUID}",
            parameters={"event_id": str(AMBIGUOUS_EVENT_ID)},
        ).result_rows == [(1,)]

        publish_retry_message = _raw_message(
            endpoint_id,
            event_id=PUBLISH_RETRY_EVENT_ID,
            offset=7,
            command_line="validated publish retry",
        )
        with psycopg.connect(postgres_dsn) as connection:
            publish_retry_consumer = OneMessageConsumer(publish_retry_message)
            publish_retry_producer = SequencedProducer([False, True])
            publish_retry_worker = EventStorageWorker(
                consumer=publish_retry_consumer,
                producer=publish_retry_producer,
                events=EventRepository.for_ingest(clickhouse),
                registry=EventIngestRegistryRepository(connection),
                metadata=IngestMetadataRepository(connection),
                failure_sink=CapturingFailureSink(),
                sleep=lambda _delay: None,
                now=lambda: NOW,
            )
            assert publish_retry_worker.run_once() is True
            assert publish_retry_consumer.committed == [7]
            assert len(publish_retry_producer.messages) == 2
            assert connection.execute(
                "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                (PUBLISH_RETRY_EVENT_ID,),
            ).fetchone()[0] == 1
        assert clickhouse.query(
            "SELECT count() FROM edr_events WHERE event_id = {event_id:UUID}",
            parameters={"event_id": str(PUBLISH_RETRY_EVENT_ID)},
        ).result_rows == [(1,)]

        duplicate_message = _raw_message(
            endpoint_id,
            event_id=LEGACY_DUPLICATE_EVENT_ID,
            offset=8,
            command_line="preexisting duplicate",
        )
        duplicate_record = normalize_event(json.loads(duplicate_message.value), ingested_at=NOW)
        EventRepository.for_maintenance(clickhouse).insert([duplicate_record])
        EventRepository.for_maintenance(clickhouse).insert([duplicate_record])

        first_conflict_message = _raw_message(
            endpoint_id,
            event_id=LEGACY_CONFLICT_EVENT_ID,
            offset=9,
            command_line="first preexisting identity",
        )
        second_conflict_message = _raw_message(
            endpoint_id,
            event_id=LEGACY_CONFLICT_EVENT_ID,
            offset=10,
            command_line="second preexisting identity",
        )
        EventRepository.for_maintenance(clickhouse).insert(
            [normalize_event(json.loads(first_conflict_message.value), ingested_at=NOW)]
        )
        EventRepository.for_maintenance(clickhouse).insert(
            [normalize_event(json.loads(second_conflict_message.value), ingested_at=NOW)]
        )

        with psycopg.connect(postgres_dsn) as connection:
            legacy_conflict_consumer = OneMessageConsumer(first_conflict_message)
            legacy_conflict_producer = CapturingProducer()
            legacy_conflict_sink = CapturingFailureSink()
            legacy_conflict_worker = EventStorageWorker(
                consumer=legacy_conflict_consumer,
                producer=legacy_conflict_producer,
                events=EventRepository.for_ingest(clickhouse),
                registry=EventIngestRegistryRepository(connection),
                metadata=IngestMetadataRepository(connection),
                failure_sink=legacy_conflict_sink,
                sleep=lambda _delay: None,
                now=lambda: NOW,
            )
            assert legacy_conflict_worker.run_once() is True
            assert legacy_conflict_consumer.committed == [9]
            assert legacy_conflict_producer.messages == []
            assert legacy_conflict_sink.records[0]["failure_code"] == "EVENT_IDENTITY_CONFLICT"
            assert connection.execute(
                "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                (LEGACY_CONFLICT_EVENT_ID,),
            ).fetchone()[0] == 0

        duplicate_audit = audit_event_duplicates(clickhouse, limit=10)
        assert duplicate_audit.duplicate_event_ids == 2
        assert duplicate_audit.extra_physical_rows == 2
        assert duplicate_audit.conflicting_event_ids == 1
        findings = {finding.event_id: finding for finding in duplicate_audit.findings}
        assert findings[str(LEGACY_DUPLICATE_EVENT_ID)].identity_count == 1
        assert findings[str(LEGACY_CONFLICT_EVENT_ID)].identity_count == 2
    finally:
        clickhouse.command("SYSTEM START MERGES edr_events")
        apply_clickhouse_file(clickhouse, clickhouse_down)
        clickhouse.close()
        with psycopg.connect(postgres_dsn) as connection:
            apply_postgres_migrations(connection, postgres_migrations, direction="down")
