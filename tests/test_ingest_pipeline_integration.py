import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import boto3
import clickhouse_connect
import psycopg
import pytest
from confluent_kafka.admin import AdminClient
from fastapi.testclient import TestClient

from backend.detection import DetectionEngine
from backend.failure import FailureSink
from backend.kafka import RAW_TOPIC, TOPICS, KafkaConsumer, ensure_topics
from backend.main import create_app
from backend.runtime import RuntimeServices
from backend.settings import Settings
from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_migrations
from backend.storage.postgres import AlertRepository, EndpointRepository, IncidentRepository, IngestMetadataRepository
from backend.workers import DetectionWorker, EventStorageWorker, LifecycleTasks
from tools.replay_failure import FailureNotFoundError, replay_failure

ROOT = Path(__file__).parents[1]
RUN_INTEGRATION = os.getenv("EDR_RUN_INGEST_INTEGRATION") == "1"
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not RUN_INTEGRATION, reason="ingest integration disabled")]


def cert_headers(agent_id: str, fingerprint: str) -> dict[str, str]:
    return {
        "X-EDR-mTLS-Verify": "SUCCESS",
        "X-EDR-Certificate-Subject": f"CN={agent_id}",
        "X-EDR-Certificate-SAN-Agent-ID": agent_id,
        "X-EDR-Certificate-Fingerprint-SHA256": fingerprint,
        "X-EDR-Certificate-Not-Before": "Jul 11 00:00:00 2026 GMT",
        "X-EDR-Certificate-Not-After": "Jul 20 00:00:00 2026 GMT",
    }


def registration(agent_id: str = "agent-win-001") -> dict:
    return {
        "agentId": agent_id,
        "hostname": "WIN-ENDPOINT-01",
        "osType": "WINDOWS",
        "osVersion": "11",
        "agentVersion": "0.1.0",
        "agentBuildId": "win-x64-1",
        "agentArch": "X64",
        "capabilityCodes": ["PROCESS_EXECUTION", "DNS_QUERY"],
    }


def heartbeat(agent_id: str = "agent-win-001", sensors: list[dict] | None = None) -> dict:
    return {
        "agentId": agent_id,
        "agentVersion": "0.1.0",
        "agentBuildId": "win-x64-1",
        "agentArch": "X64",
        "capabilityCodes": ["PROCESS_EXECUTION"],
        "bufferDepth": 0,
        "sensorHealth": sensors or [{"sensor": "PROCESS", "status": "HEALTHY"}],
        "sentAt": "2026-07-12T00:00:00Z",
    }


def telemetry(event_id: UUID, batch_id: UUID, *, command_line: str, occurred_at: datetime) -> dict:
    timestamp = occurred_at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "schemaVersion": 1,
        "batchId": str(batch_id),
        "agentId": "agent-win-001",
        "sentAt": timestamp,
        "events": [
            {
                "eventId": str(event_id),
                "eventType": "PROCESS_EXECUTION",
                "occurredAt": timestamp,
                "payload": {"processName": "powershell.exe", "pid": 42, "commandLine": command_line},
            }
        ],
    }


def consume_until(worker, attempts: int = 30) -> None:
    for _ in range(attempts):
        if worker.run_once(1.0):
            return
    raise AssertionError("worker did not consume a message")


class AlwaysFailEvents:
    def identity(self, event_id):
        raise RuntimeError("temporary ClickHouse failure")


def test_actual_http_kafka_storage_detection_failure_and_replay_flow() -> None:
    postgres_dsn = os.environ["TEST_POSTGRES_DSN"]
    clickhouse_password = os.environ["TEST_CLICKHOUSE_PASSWORD"]
    s3_endpoint = os.getenv("TEST_S3_ENDPOINT", "http://127.0.0.1:59000")
    s3_access_key = os.getenv("TEST_S3_ACCESS_KEY", "edr-local")
    s3_secret_key = os.environ["TEST_S3_SECRET_KEY"]
    s3_bucket = "edr-failures"
    bootstrap = os.getenv("TEST_KAFKA_BOOTSTRAP", "127.0.0.1:59092")
    clickhouse = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=58123,
        username="edr",
        password=clickhouse_password,
        database="edr",
    )
    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=s3_access_key,
        aws_secret_access_key=s3_secret_key,
        region_name="us-east-1",
    )
    try:
        s3.create_bucket(Bucket=s3_bucket)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass

    postgres_migrations = ROOT / "migrations/postgresql"
    clickhouse_down = ROOT / "migrations/clickhouse/0001_initial.down.sql"
    clickhouse_up = ROOT / "migrations/clickhouse/0001_initial.up.sql"
    with psycopg.connect(postgres_dsn) as connection:
        apply_postgres_migrations(connection, postgres_migrations, direction="down")
        apply_postgres_migrations(connection, postgres_migrations)
    apply_clickhouse_file(clickhouse, clickhouse_down)
    apply_clickhouse_file(clickhouse, clickhouse_up)
    admin = AdminClient({"bootstrap.servers": bootstrap})
    metadata = admin.list_topics(timeout=10)
    existing_topics = [topic for topic in TOPICS if topic in metadata.topics]
    if existing_topics:
        for future in admin.delete_topics(existing_topics).values():
            future.result(10)
    ensure_topics(bootstrap)

    settings = Settings(
        jwt_secret="test-jwt",
        postgres_dsn=postgres_dsn,
        clickhouse_dsn=f"http://edr:{clickhouse_password}@127.0.0.1:58123/edr",
        kafka_bootstrap_servers=bootstrap,
        s3_endpoint_url=s3_endpoint,
        s3_access_key_id=s3_access_key,
        s3_secret_access_key=s3_secret_key,
        s3_bucket=s3_bucket,
        agent_ca_cert_path="certs/ca.crt",
        agent_ca_key_path="certs/ca.key",
        _env_file=None,
    )
    runtime = RuntimeServices(settings)
    raw_consumer = KafkaConsumer(bootstrap, group_id=f"ingest-storage-{uuid4()}", topic=RAW_TOPIC)
    detection_consumer = KafkaConsumer(
        bootstrap,
        group_id=f"ingest-detection-{uuid4()}",
        topic="telemetry.validated",
    )
    client = TestClient(create_app(runtime))
    fingerprint_a = "a" * 64
    fingerprint_b = "b" * 64
    now = datetime.now(UTC)
    event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e001")
    try:
        first = client.post(
            "/api/v1/collector/agents/register",
            headers=cert_headers("agent-win-001", fingerprint_a),
            json=registration(),
        )
        same = client.post(
            "/api/v1/collector/agents/register",
            headers=cert_headers("agent-win-001", fingerprint_a),
            json=registration(),
        )
        rotation = client.post(
            "/api/v1/collector/agents/register",
            headers=cert_headers("agent-win-001", fingerprint_b),
            json=registration(),
        )
        conflict = client.post(
            "/api/v1/collector/agents/register",
            headers=cert_headers("agent-other-001", fingerprint_b),
            json=registration("agent-other-001"),
        )
        assert (first.status_code, same.status_code, rotation.status_code, conflict.status_code) == (201, 200, 200, 409)

        inactive = client.post(
            "/api/v1/collector/agents/heartbeat",
            headers=cert_headers("agent-win-001", fingerprint_a),
            json=heartbeat(),
        )
        assert inactive.status_code == 401
        snapshot = client.post(
            "/api/v1/collector/agents/heartbeat",
            headers=cert_headers("agent-win-001", fingerprint_b),
            json=heartbeat(sensors=[{"sensor": "L7", "status": "DEGRADED", "parseErrorCount": 3}]),
        )
        assert snapshot.status_code == 200
        with runtime.postgres() as connection:
            endpoint_id, sensors = connection.execute(
                "SELECT endpoint_id, sensor_health_json FROM endpoints WHERE agent_id = 'agent-win-001'"
            ).fetchone()
        assert sensors == [{"sensor": "L7", "status": "DEGRADED", "parseErrorCount": 3}]

        normal = telemetry(
            event_id,
            UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e000"),
            command_line="powershell.exe -EncodedCommand ZQBjAGgAbwA=",
            occurred_at=now,
        )
        future = dict(normal["events"][0])
        future["eventId"] = "018ff8f4-86de-7b25-9b8a-2d22f6a3e002"
        future["occurredAt"] = (now + timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
        normal["events"].append(future)
        accepted = client.post(
            "/api/v1/collector/telemetry/batches",
            headers=cert_headers("agent-win-001", fingerprint_b),
            json=normal,
        )
        assert accepted.status_code == 200
        assert accepted.json()["data"]["acceptedEventIds"] == [str(event_id)]
        assert accepted.json()["data"]["rejectedEvents"][0]["code"] == "EVENT_TIME_IN_FUTURE"
        assert (
            client.post(
                "/api/v1/collector/telemetry/batches",
                headers=cert_headers("agent-win-001", fingerprint_b),
                json={},
            ).status_code
            == 400
        )
        too_many = dict(normal)
        too_many["events"] = [normal["events"][0] for _ in range(101)]
        assert (
            client.post(
                "/api/v1/collector/telemetry/batches",
                headers=cert_headers("agent-win-001", fingerprint_b),
                json=too_many,
            ).status_code
            == 413
        )

        failure_repository = FailureRepository(runtime.clickhouse)
        failure_sink = FailureSink(s3_client=runtime.s3, bucket=s3_bucket, repository=failure_repository)
        with runtime.postgres() as connection:
            storage_worker = EventStorageWorker(
                consumer=raw_consumer,
                producer=runtime.producer,
                events=EventRepository(runtime.clickhouse),
                metadata=IngestMetadataRepository(connection),
                failure_sink=failure_sink,
                sleep=lambda _delay: None,
            )
            consume_until(storage_worker)
        assert EventRepository(runtime.clickhouse).identity(event_id) is not None

        with runtime.postgres() as connection:
            detection_worker = DetectionWorker(
                consumer=detection_consumer,
                engine=DetectionEngine(runtime.rules),
                alerts=AlertRepository(connection),
                incidents=IncidentRepository(connection),
                failure_sink=failure_sink,
                sleep=lambda _delay: None,
            )
            consume_until(detection_worker)
            counts = connection.execute(
                "SELECT (SELECT count(*) FROM alerts), (SELECT count(*) FROM incidents)"
            ).fetchone()
            incident_snapshot = connection.execute("SELECT title, description FROM incidents").fetchone()
        assert counts == (1, 1)
        assert incident_snapshot == (
            "Encoded PowerShell command detected",
            "PowerShell was executed with an encoded command argument.",
        )

        duplicate = telemetry(
            event_id,
            uuid4(),
            command_line=normal["events"][0]["payload"]["commandLine"],
            occurred_at=now,
        )
        assert (
            client.post(
                "/api/v1/collector/telemetry/batches",
                headers=cert_headers("agent-win-001", fingerprint_b),
                json=duplicate,
            ).status_code
            == 200
        )
        with runtime.postgres() as connection:
            duplicate_storage = EventStorageWorker(
                consumer=raw_consumer,
                producer=runtime.producer,
                events=EventRepository(runtime.clickhouse),
                metadata=IngestMetadataRepository(connection),
                failure_sink=failure_sink,
                sleep=lambda _delay: None,
            )
            consume_until(duplicate_storage)
            duplicate_detection = DetectionWorker(
                consumer=detection_consumer,
                engine=DetectionEngine(runtime.rules),
                alerts=AlertRepository(connection),
                incidents=IncidentRepository(connection),
                failure_sink=failure_sink,
                sleep=lambda _delay: None,
            )
            consume_until(duplicate_detection)
            assert connection.execute("SELECT count(*) FROM alerts").fetchone()[0] == 1
            assert connection.execute("SELECT count(*) FROM incidents").fetchone()[0] == 1

        retry_event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e010")
        retry_payload = telemetry(retry_event_id, uuid4(), command_line="notepad.exe", occurred_at=now)
        client.post(
            "/api/v1/collector/telemetry/batches",
            headers=cert_headers("agent-win-001", fingerprint_b),
            json=retry_payload,
        )
        with runtime.postgres() as connection:
            failed_worker = EventStorageWorker(
                consumer=raw_consumer,
                producer=runtime.producer,
                events=AlwaysFailEvents(),
                metadata=IngestMetadataRepository(connection),
                failure_sink=failure_sink,
                sleep=lambda _delay: None,
            )
            consume_until(failed_worker)
        failure_id = UUID(
            str(
                runtime.clickhouse.query(
                    "SELECT failure_id FROM event_failures FINAL WHERE event_id = {event_id:UUID} LIMIT 1",
                    parameters={"event_id": str(retry_event_id)},
                ).result_rows[0][0]
            )
        )
        failure = failure_repository.latest(failure_id)
        assert failure is not None
        assert s3.head_object(Bucket=s3_bucket, Key=str(failure["payload_object_key"]))["ContentLength"] > 0
        replay_failure(failure_id, runtime, now=datetime.now(UTC))
        assert failure_repository.latest_status(failure_id) == "REPROCESSED"
        with runtime.postgres() as connection:
            replay_worker = EventStorageWorker(
                consumer=raw_consumer,
                producer=runtime.producer,
                events=EventRepository(runtime.clickhouse),
                metadata=IngestMetadataRepository(connection),
                failure_sink=failure_sink,
                sleep=lambda _delay: None,
            )
            consume_until(replay_worker)
        assert EventRepository(runtime.clickhouse).identity(retry_event_id) is not None
        with pytest.raises(FailureNotFoundError):
            replay_failure(uuid4(), runtime, now=datetime.now(UTC))
        latest_failure = failure_repository.latest(failure_id)
        assert latest_failure is not None
        s3.put_object(
            Bucket=s3_bucket,
            Key=str(latest_failure["payload_object_key"]),
            Body=b"corrupted failure payload",
        )
        with pytest.raises(ValueError, match="size mismatch"):
            replay_failure(failure_id, runtime, now=datetime.now(UTC))
        assert failure_repository.latest_status(failure_id) == "REPROCESS_FAILED"

        with runtime.postgres() as connection:
            connection.execute(
                "UPDATE endpoints SET status = 'RETIRED', last_seen_at = %s",
                (now - timedelta(minutes=5),),
            )
            connection.commit()
            lifecycle = LifecycleTasks(EndpointRepository(connection), IncidentRepository(connection))
            assert lifecycle.run_once(now=now)[0] == 0
            status = connection.execute(
                "SELECT status FROM endpoints WHERE endpoint_id = %s",
                (endpoint_id,),
            ).fetchone()[0]
            assert status == "RETIRED"
        assert (
            client.post(
                "/api/v1/collector/agents/register",
                headers=cert_headers("agent-win-001", fingerprint_b),
                json=registration(),
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/collector/agents/heartbeat",
                headers=cert_headers("agent-win-001", fingerprint_b),
                json=heartbeat(),
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/collector/telemetry/batches",
                headers=cert_headers("agent-win-001", fingerprint_b),
                json=telemetry(uuid4(), uuid4(), command_line="notepad.exe", occurred_at=now),
            ).status_code
            == 403
        )
        keys = [item["Key"] for item in s3.list_objects_v2(Bucket=s3_bucket).get("Contents", [])]
        assert all("pcap" not in key.lower() for key in keys)
    finally:
        raw_consumer.close()
        detection_consumer.close()
        with psycopg.connect(postgres_dsn) as connection:
            apply_postgres_migrations(connection, postgres_migrations, direction="down")
        apply_clickhouse_file(clickhouse, clickhouse_down)
        response = s3.list_objects_v2(Bucket=s3_bucket)
        for item in response.get("Contents", []):
            s3.delete_object(Bucket=s3_bucket, Key=item["Key"])
        s3.delete_bucket(Bucket=s3_bucket)
        clickhouse.close()
