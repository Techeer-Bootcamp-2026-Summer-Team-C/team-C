import gzip
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from backend.contracts.enums import AlertStatus, IncidentStatus
from backend.detection import DetectionEngine
from backend.failure import FailureSink, deterministic_failure_payload, failure_id_for
from backend.kafka import RAW_TOPIC, VALIDATED_TOPIC, ConsumedMessage
from backend.rule_loader import RuleLoader
from backend.storage.models import EventIdentity, StoredAlert, StoredIncident
from backend.workers import DetectionWorker, EventStorageWorker, LifecycleTasks

NOW = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
EVENT_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e001")
ROOT = Path(__file__).parents[1]


def raw_message(command_line: str = "powershell.exe -EncodedCommand ZQBjAGgAbwA=") -> bytes:
    return json.dumps(
        {
            "schemaVersion": 1,
            "batchId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e000",
            "endpointId": 1001,
            "agentId": "agent-win-001",
            "hostname": "WIN-ENDPOINT-01",
            "osType": "WINDOWS",
            "ipAddress": None,
            "event": {
                "eventId": str(EVENT_ID),
                "eventType": "PROCESS_EXECUTION",
                "occurredAt": "2026-07-12T00:59:59Z",
                "payload": {"processName": "powershell.exe", "pid": 42, "commandLine": command_line},
            },
        },
        separators=(",", ":"),
    ).encode()


def message(value: bytes, *, topic: str = RAW_TOPIC, offset: int = 1) -> ConsumedMessage:
    return ConsumedMessage(topic, 0, offset, b"1001", value, [])


class QueueConsumer:
    def __init__(self, messages: list[ConsumedMessage]) -> None:
        self.messages = messages
        self.committed: list[int] = []
        self.rewound: list[int] = []

    def consume_one(self, timeout=1.0):
        return self.messages.pop(0) if self.messages else None

    def commit(self, item):
        self.committed.append(item.offset)

    def rewind(self, item):
        self.rewound.append(item.offset)


class CapturingProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, bytes]] = []

    def publish(self, topic, *, key, value, headers=None):
        self.messages.append((topic, key, value))
        return True

    def check(self):
        return None


class MemoryEvents:
    def __init__(self) -> None:
        self.rows = {}
        self.insert_count = 0

    def identity(self, event_id):
        row = self.rows.get(event_id)
        if row is None:
            return None
        return EventIdentity(event_id, row["endpoint_id"], row["agent_id"], row["payload_sha256"])

    def insert(self, rows):
        self.insert_count += len(rows)
        for row in rows:
            self.rows[row["event_id"]] = row


class Metadata:
    @contextmanager
    def hot_ingest_guard(self, **kwargs):
        yield


class Sink:
    def __init__(self, fail=False) -> None:
        self.records = []
        self.fail = fail

    def record(self, item, **kwargs):
        if self.fail:
            raise RuntimeError("sink down")
        self.records.append((item, kwargs))


def test_storage_worker_saves_publishes_and_deduplicates() -> None:
    consumer = QueueConsumer([message(raw_message()), message(raw_message(), offset=2)])
    producer = CapturingProducer()
    events = MemoryEvents()
    worker = EventStorageWorker(
        consumer=consumer,
        producer=producer,
        events=events,
        metadata=Metadata(),
        failure_sink=Sink(),
        sleep=lambda _delay: None,
        now=lambda: NOW,
    )
    assert worker.run_once() is True
    assert worker.run_once() is True
    assert events.insert_count == 1
    assert [topic for topic, _key, _value in producer.messages] == [VALIDATED_TOPIC, VALIDATED_TOPIC]
    assert [key for _topic, key, _value in producer.messages] == ["1001", "1001"]
    assert consumer.committed == [1, 2]


def test_identity_conflict_is_durable_failure_and_sink_failure_does_not_commit() -> None:
    events = MemoryEvents()
    first_consumer = QueueConsumer([message(raw_message())])
    EventStorageWorker(
        consumer=first_consumer,
        producer=CapturingProducer(),
        events=events,
        metadata=Metadata(),
        failure_sink=Sink(),
        sleep=lambda _delay: None,
        now=lambda: NOW,
    ).run_once()

    conflict = message(raw_message("different payload"), offset=3)
    durable_consumer = QueueConsumer([conflict])
    durable_sink = Sink()
    EventStorageWorker(
        consumer=durable_consumer,
        producer=CapturingProducer(),
        events=events,
        metadata=Metadata(),
        failure_sink=durable_sink,
        sleep=lambda _delay: None,
        now=lambda: NOW,
    ).run_once()
    assert durable_consumer.committed == [3]
    assert durable_sink.records[0][1]["failure_code"] == "EVENT_IDENTITY_CONFLICT"

    failed_consumer = QueueConsumer([message(raw_message("another payload"), offset=4)])
    EventStorageWorker(
        consumer=failed_consumer,
        producer=CapturingProducer(),
        events=events,
        metadata=Metadata(),
        failure_sink=Sink(fail=True),
        sleep=lambda _delay: None,
        now=lambda: NOW,
    ).run_once()
    assert failed_consumer.committed == []
    assert failed_consumer.rewound == [4]


def test_storage_worker_quarantines_invalid_message_without_retrying() -> None:
    consumer = QueueConsumer([message(b"not-json", offset=5)])
    sink = Sink()
    sleeps: list[float] = []
    worker = EventStorageWorker(
        consumer=consumer,
        producer=CapturingProducer(),
        events=MemoryEvents(),
        metadata=Metadata(),
        failure_sink=sink,
        sleep=sleeps.append,
        now=lambda: NOW,
    )

    assert worker.run_once() is True
    assert sleeps == []
    assert consumer.committed == [5]
    assert sink.records[0][1]["failure_code"] == "INVALID_MESSAGE"
    assert sink.records[0][1]["retryable"] is False
    assert sink.records[0][1]["retry_count"] == 0


def test_storage_worker_requests_connection_reset_after_retry_exhaustion() -> None:
    class BrokenEvents:
        def identity(self, _event_id):
            raise RuntimeError("database connection lost")

    worker = EventStorageWorker(
        consumer=QueueConsumer([message(raw_message(), offset=7)]),
        producer=CapturingProducer(),
        events=BrokenEvents(),
        metadata=Metadata(),
        failure_sink=Sink(),
        sleep=lambda _delay: None,
        now=lambda: NOW,
    )
    assert worker.run_once() is True
    assert worker.reset_requested is True


class MemoryAlerts:
    def __init__(self) -> None:
        self.rows = {}

    def insert_if_absent(self, alert):
        key = (alert.event_id, alert.rule_code, alert.rule_version)
        created = key not in self.rows
        self.rows.setdefault(key, alert)
        return StoredAlert(1, created, AlertStatus.OPEN)


class MemoryIncidents:
    def __init__(self) -> None:
        self.rows = {}
        self.links = set()

    def upsert(self, incident):
        key = (incident.endpoint_id, incident.correlation_key, incident.window_start_at)
        created = key not in self.rows
        self.rows.setdefault(key, incident)
        return StoredIncident(1, created, IncidentStatus.OPEN)

    def link_alert(self, *, incident_id, alert_id, linked_at):
        self.links.add((incident_id, alert_id))


def test_detection_worker_creates_idempotent_alert_and_incident_with_first_snapshot() -> None:
    storage_consumer = QueueConsumer([message(raw_message())])
    producer = CapturingProducer()
    EventStorageWorker(
        consumer=storage_consumer,
        producer=producer,
        events=MemoryEvents(),
        metadata=Metadata(),
        failure_sink=Sink(),
        sleep=lambda _delay: None,
        now=lambda: NOW,
    ).run_once()
    validated = producer.messages[0][2]
    consumer = QueueConsumer(
        [message(validated, topic=VALIDATED_TOPIC, offset=1), message(validated, topic=VALIDATED_TOPIC, offset=2)]
    )
    loader = RuleLoader(
        schema_path=ROOT / "schemas/rule-v1.schema.json",
        mapping_path=ROOT / "mappings/mitre_attack.yaml",
    )
    alerts = MemoryAlerts()
    incidents = MemoryIncidents()
    worker = DetectionWorker(
        consumer=consumer,
        engine=DetectionEngine(loader.load_directory(ROOT / "rules")),
        alerts=alerts,
        incidents=incidents,
        failure_sink=Sink(),
        sleep=lambda _delay: None,
        now=lambda: NOW,
    )
    worker.run_once()
    worker.run_once()
    assert len(alerts.rows) == 1
    assert len(incidents.rows) == 1
    incident = next(iter(incidents.rows.values()))
    assert incident.title == "Encoded PowerShell command detected"
    assert incident.description == "PowerShell was executed with an encoded command argument."
    assert len(incidents.links) == 1


def test_detection_worker_quarantines_invalid_message_without_retrying() -> None:
    consumer = QueueConsumer([message(b"[]", topic=VALIDATED_TOPIC, offset=6)])
    sink = Sink()
    sleeps: list[float] = []
    worker = DetectionWorker(
        consumer=consumer,
        engine=SimpleNamespace(),
        alerts=SimpleNamespace(),
        incidents=SimpleNamespace(),
        failure_sink=sink,
        sleep=sleeps.append,
        now=lambda: NOW,
    )

    assert worker.run_once() is True
    assert sleeps == []
    assert consumer.committed == [6]
    assert sink.records[0][1]["failure_code"] == "INVALID_MESSAGE"
    assert sink.records[0][1]["retryable"] is False


def test_detection_worker_requests_connection_reset_after_retry_exhaustion() -> None:
    validated = json.dumps(
        {
            "event": {
                "event_id": str(EVENT_ID),
                "endpoint_id": 1001,
                "agent_id": "agent-win-001",
                "event_type": "PROCESS_EXECUTION",
                "occurred_at": "2026-07-12T00:59:59Z",
            }
        }
    ).encode()

    class BrokenEngine:
        def evaluate(self, *_args, **_kwargs):
            raise RuntimeError("database connection lost")

    worker = DetectionWorker(
        consumer=QueueConsumer([message(validated, topic=VALIDATED_TOPIC, offset=8)]),
        engine=BrokenEngine(),
        alerts=SimpleNamespace(),
        incidents=SimpleNamespace(),
        failure_sink=Sink(),
        sleep=lambda _delay: None,
        now=lambda: NOW,
    )
    assert worker.run_once() is True
    assert worker.reset_requested is True


def test_lifecycle_uses_two_minute_cutoff() -> None:
    class Endpoints:
        def mark_offline(self, *, cutoff, updated_at):
            assert cutoff == NOW.replace(minute=58, hour=0)
            return 1

    class Incidents:
        def close_expired(self, now):
            assert now == NOW
            return 2

    assert LifecycleTasks(Endpoints(), Incidents()).run_once(now=NOW) == (1, 2)


def test_failure_identity_and_gzip_are_deterministic() -> None:
    item = message(raw_message())
    first_id = failure_id_for(item, "event-storage-worker", "EVENT_STORAGE")
    second_id = failure_id_for(item, "event-storage-worker", "EVENT_STORAGE")
    envelope = {"message": json.loads(item.value), "sourceTopic": item.topic}
    assert first_id == second_id
    assert deterministic_failure_payload(envelope) == deterministic_failure_payload(envelope)
    assert b"pcap" not in deterministic_failure_payload(envelope).lower()


def test_failure_sink_preserves_malformed_poison_message() -> None:
    class MissingObject(Exception):
        response = {"ResponseMetadata": {"HTTPStatusCode": 404}}

    class S3:
        objects: dict[str, bytes] = {}

        def head_object(self, *, Bucket, Key):
            if Key not in self.objects:
                raise MissingObject()
            return {"ContentLength": len(self.objects[Key]), "Metadata": {}}

        def put_object(self, *, Bucket, Key, Body, **_kwargs):
            self.objects[Key] = Body

        def get_object(self, *, Bucket, Key):
            raise AssertionError("existing payload lookup was not expected")

    class Failures:
        rows: list[dict[str, object]] = []

        def insert(self, rows):
            self.rows.extend(rows)

        def latest_status(self, _failure_id):
            return "FAILED"

    s3 = S3()
    failures = Failures()
    poison = message(b"\xffnot-json", offset=99)

    stored = FailureSink(s3_client=s3, bucket="failures", repository=failures).record(
        poison,
        consumer_name="event-storage-worker",
        failure_stage="EVENT_STORAGE",
        failure_code=None,
        error_message="invalid message",
        retryable=False,
        retry_count=0,
        failed_at=NOW,
    )

    payload = json.loads(gzip.decompress(s3.objects[stored.object_key]))
    assert payload["message"] == {"encoding": "base64", "raw": "/25vdC1qc29u"}
    assert failures.rows[0]["event_id"] is None
    assert failures.rows[0]["endpoint_id"] is None
