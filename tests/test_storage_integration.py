import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import clickhouse_connect
import psycopg
import pytest

from backend.contracts.enums import AlertStatus, OsType, Severity, StorageBackend, StorageClass, StorageStatus
from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_file
from backend.storage.models import AlertInsert, EndpointInsert, IncidentInsert, IngestBucket
from backend.storage.postgres import AlertRepository, EndpointRepository, IncidentRepository, IngestMetadataRepository

ROOT = Path(__file__).parents[1]
RUN_INTEGRATION = os.getenv("EDR_RUN_STORAGE_INTEGRATION") == "1"


pytestmark = [pytest.mark.integration, pytest.mark.skipif(not RUN_INTEGRATION, reason="storage integration disabled")]


def test_postgresql_migration_repository_idempotency_and_rollback() -> None:
    dsn = os.environ["TEST_POSTGRES_DSN"]
    now = datetime(2026, 7, 12, tzinfo=UTC)
    with psycopg.connect(dsn) as connection:
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0001_initial.down.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0001_initial.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0002_user_login_id.up.sql")
        connection.execute(
            """
            INSERT INTO users (login_id, password_hash, name, role, status, created_at, updated_at)
            VALUES ('migration-user', 'hash', 'Migration User', 'VIEWER', 'ACTIVE', %s, %s)
            """,
            (now, now),
        )
        connection.commit()
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0003_user_locale.up.sql")
        assert connection.execute("SELECT locale FROM users WHERE login_id = 'migration-user'").fetchone()[0] == "EN"
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                connection.execute("UPDATE users SET locale = 'JA' WHERE login_id = 'migration-user'")
        column = connection.execute(
            """
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'login_id'
            """
        ).fetchone()
        assert column == ("character varying", 64)
        index_definition = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'uq_users_login_id_active'"
        ).fetchone()[0]
        assert "lower" in index_definition.lower()
        assert "is_delete" in index_definition.lower()
        try:
            endpoint_id = EndpointRepository(connection).insert(
                EndpointInsert("agent-test-001", "TEST-ENDPOINT", OsType.MACOS, now)
            )
            alert_insert = AlertInsert(
                endpoint_id=endpoint_id,
                event_id=UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e001"),
                event_occurred_at=now,
                batch_id=UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e000"),
                agent_id="agent-test-001",
                rule_code="PROC_POWERSHELL_ENCODED",
                rule_name="PowerShell Encoded Command",
                rule_version=1,
                mitre_tactic_code="TA0002",
                mitre_tactic_name="Execution",
                mitre_technique_code="T1059.001",
                mitre_technique_name="PowerShell",
                title="Encoded PowerShell command detected",
                summary="PowerShell was executed with an encoded command argument.",
                severity=Severity.HIGH,
                risk_score=Decimal("85"),
                detected_at=now,
            )
            alerts = AlertRepository(connection)
            first = alerts.insert_if_absent(alert_insert)
            second = alerts.insert_if_absent(alert_insert)
            assert first.created is True
            assert second.created is False
            assert first.alert_id == second.alert_id
            assert len(alerts.active_for_endpoint(endpoint_id)) == 1

            incidents = IncidentRepository(connection)
            incident = incidents.upsert(
                IncidentInsert(
                    endpoint_id,
                    "suspicious-powershell",
                    now,
                    now + timedelta(minutes=30),
                    "PowerShell correlation",
                    None,
                    Severity.HIGH,
                    now,
                )
            )
            incidents.link_alert(incident_id=incident.incident_id, alert_id=first.alert_id, linked_at=now)
            incidents.link_alert(incident_id=incident.incident_id, alert_id=first.alert_id, linked_at=now)
            assert len(incidents.open_for_endpoint(endpoint_id)) == 1

            metadata = IngestMetadataRepository(connection)
            metadata.upsert(
                IngestBucket(
                    endpoint_id,
                    now,
                    now + timedelta(days=1),
                    StorageBackend.CLICKHOUSE,
                    StorageClass.HOT,
                    StorageStatus.HOT,
                    f"clickhouse://edr_events/date=2026-07-12/endpoint_id={endpoint_id}",
                ),
                now,
            )
            assert len(metadata.overlapping([endpoint_id], now + timedelta(hours=1), now + timedelta(hours=2))) == 1

            archive_start = now + timedelta(days=1)
            metadata.upsert(
                IngestBucket(
                    endpoint_id,
                    archive_start,
                    archive_start + timedelta(days=1),
                    StorageBackend.S3,
                    StorageClass.GLACIER_FLEXIBLE_RETRIEVAL,
                    StorageStatus.ARCHIVED,
                    f"archives/date=2026-07-13/endpoint_id={endpoint_id}/events.parquet",
                ),
                now,
            )
            assert len(metadata.restore_buckets([endpoint_id], archive_start, archive_start + timedelta(days=1))) == 1
            assert (
                metadata.request_restore(
                    endpoint_id=endpoint_id,
                    bucket_start_at=archive_start,
                    actor_identifier="integration-test",
                    request_id="req_restore",
                    requested_at=now,
                )
                is True
            )
            assert (
                metadata.request_restore(
                    endpoint_id=endpoint_id,
                    bucket_start_at=archive_start,
                    actor_identifier="integration-test",
                    request_id="req_restore_repeat",
                    requested_at=now,
                )
                is False
            )
            assert (
                metadata.mark_restore_failed(
                    endpoint_id=endpoint_id,
                    bucket_start_at=archive_start,
                    error="temporary restore failure",
                    failed_at=now + timedelta(minutes=1),
                )
                is True
            )
            assert (
                metadata.request_restore(
                    endpoint_id=endpoint_id,
                    bucket_start_at=archive_start,
                    actor_identifier="integration-test",
                    request_id="req_restore_retry",
                    requested_at=now + timedelta(minutes=2),
                )
                is True
            )
            restore_expires_at = now + timedelta(days=7)
            assert (
                metadata.mark_restored(
                    endpoint_id=endpoint_id,
                    bucket_start_at=archive_start,
                    restored_at=now + timedelta(minutes=3),
                    restore_expires_at=restore_expires_at,
                )
                is True
            )
            assert metadata.expire_restores(restore_expires_at) == 1

            alerts.update_status_with_audit(
                alert_id=first.alert_id,
                status=AlertStatus.RESOLVED,
                actor_identifier="integration-test",
                request_id="req_integration",
                changed_at=now + timedelta(minutes=1),
            )
            assert alerts.active_for_endpoint(endpoint_id) == []
            assert incidents.close_expired(now + timedelta(hours=1)) == 1
        finally:
            apply_postgres_file(connection, ROOT / "migrations/postgresql/0003_user_locale.down.sql")
            apply_postgres_file(connection, ROOT / "migrations/postgresql/0002_user_login_id.down.sql")
            apply_postgres_file(connection, ROOT / "migrations/postgresql/0001_initial.down.sql")


def test_clickhouse_migration_event_repository_and_rollback() -> None:
    client = clickhouse_connect.get_client(
        host=os.getenv("TEST_CLICKHOUSE_HOST", "127.0.0.1"),
        port=int(os.getenv("TEST_CLICKHOUSE_PORT", "58123")),
        username=os.getenv("TEST_CLICKHOUSE_USER", "edr"),
        password=os.environ["TEST_CLICKHOUSE_PASSWORD"],
        database=os.getenv("TEST_CLICKHOUSE_DATABASE", "edr"),
    )
    down = ROOT / "migrations/clickhouse/0001_initial.down.sql"
    up = ROOT / "migrations/clickhouse/0001_initial.up.sql"
    apply_clickhouse_file(client, down)
    apply_clickhouse_file(client, up)
    try:
        now = datetime(2026, 7, 12, tzinfo=UTC)
        event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e001")
        event = {
            "event_id": event_id,
            "batch_id": UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e000"),
            "endpoint_id": 1001,
            "agent_id": "agent-test-001",
            "hostname": "TEST-ENDPOINT",
            "os_type": "MACOS",
            "ip_address": None,
            "event_type": "DNS_QUERY",
            "occurred_at": now,
            "ingested_at": now,
            "process_name": None,
            "process_path": None,
            "pid": None,
            "ppid": None,
            "command_line": None,
            "user_name": None,
            "file_path": None,
            "file_action": None,
            "file_hash_sha256": None,
            "remote_ip": None,
            "remote_domain": None,
            "remote_port": None,
            "protocol": None,
            "dns_query": "example.com",
            "dns_record_type": "A",
            "dns_response_code": "NOERROR",
            "dns_answers_json": "[]",
            "l7_protocol": None,
            "http_method": None,
            "http_host": None,
            "url": None,
            "http_status_code": None,
            "http_user_agent": None,
            "tls_sni": None,
            "tls_version": None,
            "tls_certificate_subject": None,
            "tls_certificate_issuer": None,
            "tls_certificate_sha256": None,
            "raw_payload": '{"query":"example.com","recordType":"A"}',
            "payload_sha256": "0" * 64,
            "schema_version": 1,
            "created_at": now,
            "updated_at": now,
            "is_delete": 0,
        }
        repository = EventRepository(client)
        repository.insert([event])
        repository.insert([event])
        identity = repository.identity(event_id)
        assert identity is not None
        assert identity.endpoint_id == 1001
        assert identity.payload_sha256 == "0" * 64
        assert repository.count_for_endpoint(1001, now, now + timedelta(seconds=1)) == 1
        assert (
            len(
                repository.list_for_endpoint(
                    endpoint_id=1001,
                    from_=now,
                    to=now + timedelta(seconds=1),
                    page=1,
                    size=50,
                )
            )
            == 1
        )

        failure_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e099")
        failure = {
            "failure_id": failure_id,
            "event_id": event_id,
            "endpoint_id": 1001,
            "source_topic": "edr.raw-events",
            "source_partition": 0,
            "source_offset": 1,
            "consumer_name": "normalization-worker",
            "failure_stage": "NORMALIZATION",
            "failure_code": "INVALID_PAYLOAD",
            "error_message": "invalid payload",
            "retryable": 0,
            "retry_count": 0,
            "payload_object_key": "failures/2026/07/12/failure.json",
            "payload_sha256": "1" * 64,
            "payload_size_bytes": 64,
            "status": "FAILED",
            "failed_at": now,
            "replay_count": 0,
            "last_replayed_at": None,
            "reprocess_outcome": None,
            "resolved_at": None,
            "retention_expires_at": now + timedelta(days=90),
            "created_at": now,
            "updated_at": now,
        }
        failures = FailureRepository(client)
        failures.insert([failure])
        assert failures.latest_status(failure_id) == "FAILED"
    finally:
        apply_clickhouse_file(client, down)
        client.close()
