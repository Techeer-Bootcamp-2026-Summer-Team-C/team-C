import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from threading import Event as ThreadEvent
from time import monotonic
from uuid import UUID

import clickhouse_connect
import psycopg
import pytest

from backend.contracts.enums import (
    AlertStatus,
    IncidentStatus,
    OsType,
    Severity,
    StorageBackend,
    StorageClass,
    StorageStatus,
)
from backend.errors import ArchivedDayImmutableError, EventIngestLockTimeoutError
from backend.rollup import DashboardRollupSynchronizer
from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_file, apply_postgres_migrations
from backend.storage.models import AlertInsert, EndpointInsert, IncidentInsert, IngestBucket
from backend.storage.postgres import (
    AlertRepository,
    EndpointRepository,
    EventIngestRegistryRepository,
    IncidentRepository,
    IngestMetadataRepository,
)
from backend.storage.rollup import DashboardEventRollupRepository

ROOT = Path(__file__).parents[1]
RUN_INTEGRATION = os.getenv("EDR_RUN_STORAGE_INTEGRATION") == "1"


pytestmark = [pytest.mark.integration, pytest.mark.skipif(not RUN_INTEGRATION, reason="storage integration disabled")]


def test_postgresql_migration_repository_idempotency_and_rollback() -> None:
    dsn = os.environ["TEST_POSTGRES_DSN"]
    now = datetime(2026, 7, 12, tzinfo=UTC)
    with psycopg.connect(dsn) as connection:
        apply_postgres_migrations(connection, ROOT / "migrations/postgresql", direction="down")
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
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0004_user_dashboard_layouts.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0005_query_search_sort_indexes.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0005_query_search_sort_indexes.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0006_backend_hardening.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0007_incident_status_override.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0008_dashboard_event_rollups.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0009_dashboard_rollup_coverage.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0010_event_ingest_registry.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0011_event_ingest_registry_append_only.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0012_dashboard_dimension_resolution.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0013_event_ingest_registry_hash_partition.up.sql")
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
        query_indexes = {
            row[0]
            for row in connection.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'public' AND indexname IN (
                    'idx_endpoints_hostname_lower_prefix',
                    'idx_endpoints_agent_id_lower_prefix',
                    'idx_alerts_detected_at'
                )
                """
            ).fetchall()
        }
        assert query_indexes == {
            "idx_endpoints_hostname_lower_prefix",
            "idx_endpoints_agent_id_lower_prefix",
            "idx_alerts_detected_at",
        }
        try:
            endpoint_id = EndpointRepository(connection).insert(
                EndpointInsert("agent-test-001", "TEST-ENDPOINT", OsType.MACOS, now)
            )
            registry = EventIngestRegistryRepository(connection)
            registry.assert_ready()
            registry_event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3d001")
            with registry.claim(
                event_id=registry_event_id,
                endpoint_id=endpoint_id,
                agent_id="agent-test-001",
                payload_sha256="0" * 64,
                registered_at=now,
            ) as first_claim:
                assert first_claim.created is True
            with registry.claim(
                event_id=registry_event_id,
                endpoint_id=endpoint_id,
                agent_id="agent-test-001",
                payload_sha256="1" * 64,
                registered_at=now,
            ) as duplicate_claim:
                assert duplicate_claim.created is False
                assert duplicate_claim.identity.payload_sha256 == "0" * 64
            assert (
                connection.execute(
                    "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                    (registry_event_id,),
                ).fetchone()[0]
                == 1
            )

            for statement in (
                "UPDATE event_ingest_registry SET registered_at = now() WHERE event_id = %s",
                "DELETE FROM event_ingest_registry WHERE event_id = %s",
                "TRUNCATE event_ingest_registry",
                "TRUNCATE event_ingest_registry_p00",
            ):
                with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="append-only"):
                    with connection.transaction():
                        parameters = () if statement.startswith("TRUNCATE") else (registry_event_id,)
                        connection.execute(statement, parameters)
            assert connection.execute(
                "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                (registry_event_id,),
            ).fetchone()[0] == 1

            rolled_back_event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3d002")
            with pytest.raises(RuntimeError, match="rollback claim"):
                with registry.claim(
                    event_id=rolled_back_event_id,
                    endpoint_id=endpoint_id,
                    agent_id="agent-test-001",
                    payload_sha256="2" * 64,
                    registered_at=now,
                ):
                    raise RuntimeError("rollback claim")
            assert (
                connection.execute(
                    "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                    (rolled_back_event_id,),
                ).fetchone()[0]
                == 0
            )

            concurrent_event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3d003")
            connection.commit()
            claim_together = Barrier(2)

            def claim_event_concurrently() -> bool:
                with psycopg.connect(dsn) as concurrent_connection:
                    claim_together.wait(timeout=10)
                    with EventIngestRegistryRepository(concurrent_connection).claim(
                        event_id=concurrent_event_id,
                        endpoint_id=endpoint_id,
                        agent_id="agent-test-001",
                        payload_sha256="3" * 64,
                        registered_at=now,
                    ) as claim:
                        return claim.created

            with ThreadPoolExecutor(max_workers=2) as executor:
                claim_results = list(executor.map(lambda _index: claim_event_concurrently(), range(2)))
            assert sorted(claim_results) == [False, True]
            assert (
                connection.execute(
                    "SELECT count(*) FROM event_ingest_registry WHERE event_id = %s",
                    (concurrent_event_id,),
                ).fetchone()[0]
                == 1
            )

            lock_timeout_event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3d004")
            claim_acquired = ThreadEvent()
            release_claim = ThreadEvent()

            def hold_event_claim() -> None:
                with psycopg.connect(dsn) as holder_connection:
                    with EventIngestRegistryRepository(holder_connection).claim(
                        event_id=lock_timeout_event_id,
                        endpoint_id=endpoint_id,
                        agent_id="agent-test-001",
                        payload_sha256="4" * 64,
                        registered_at=now,
                    ):
                        claim_acquired.set()
                        assert release_claim.wait(timeout=10)

            with ThreadPoolExecutor(max_workers=1) as executor:
                holder = executor.submit(hold_event_claim)
                assert claim_acquired.wait(timeout=10)
                try:
                    with psycopg.connect(dsn) as waiting_connection:
                        started_at = monotonic()
                        with pytest.raises(EventIngestLockTimeoutError, match="100ms"):
                            with EventIngestRegistryRepository(
                                waiting_connection,
                                lock_timeout_ms=100,
                            ).claim(
                                event_id=lock_timeout_event_id,
                                endpoint_id=endpoint_id,
                                agent_id="agent-test-001",
                                payload_sha256="4" * 64,
                                registered_at=now,
                            ):
                                pass
                        assert monotonic() - started_at < 3
                finally:
                    release_claim.set()
                holder.result(timeout=10)

            endpoint_rows = EndpointRepository(connection)
            assert [row["endpoint_id"] for row in endpoint_rows.risk_snapshot(q="test")] == [endpoint_id]
            assert [row["endpoint_id"] for row in endpoint_rows.risk_snapshot(q=str(endpoint_id))] == [endpoint_id]
            assert endpoint_rows.risk_snapshot(q="TEST%") == []
            risk_page, risk_total = endpoint_rows.risk_page(q="test", limit=1, offset=0)
            assert risk_total == 1
            assert [row["endpoint_id"] for row in risk_page] == [endpoint_id]

            rollups = DashboardEventRollupRepository(connection)
            bucket_key = (endpoint_id, now)
            activity_row = {
                "bucket_start_at": now,
                "endpoint_id": endpoint_id,
                "event_type": "DNS_QUERY",
                "event_count": 2,
                "source_max_ingested_at": now,
            }
            dimension_row = {
                "bucket_start_at": now,
                "endpoint_id": endpoint_id,
                "dimension_name": "top_dns_queries",
                "dimension_value": "example.com",
                "event_count": 2,
            }
            rollups.replace_buckets(
                bucket_keys=[bucket_key],
                dimension_bucket_keys=[(endpoint_id, now.replace(minute=0))],
                activity_rows=[activity_row],
                dimension_rows=[dimension_row],
                refreshed_at=now,
            )
            activity_row["event_count"] = 3
            dimension_row["event_count"] = 3
            rollups.replace_buckets(
                bucket_keys=[bucket_key],
                dimension_bucket_keys=[(endpoint_id, now.replace(minute=0))],
                activity_rows=[activity_row],
                dimension_rows=[dimension_row],
                refreshed_at=now + timedelta(seconds=1),
            )
            assert rollups.covers_range(from_=now, to=now + timedelta(minutes=1)) is False
            rollups.replace_range(
                from_=now,
                to=now + timedelta(minutes=1),
                activity_rows=[activity_row],
                dimension_rows=[dimension_row],
                refreshed_at=now + timedelta(seconds=2),
            )
            assert rollups.covers_range(from_=now, to=now + timedelta(minutes=1)) is True
            assert rollups.missing_ranges(from_=now, to=now + timedelta(minutes=2)) == [
                (now + timedelta(minutes=1), now + timedelta(minutes=2))
            ]
            rollup_summary = rollups.dashboard_summary(
                from_=now,
                to=now + timedelta(minutes=5),
                interval_seconds=300,
                endpoint_id=endpoint_id,
            )
            assert rollup_summary.total_count == 3
            assert rollup_summary.by_event_type == {"DNS_QUERY": 3}
            assert rollup_summary.top_dns_queries == {"example.com": 3}
            assert rollups.state()["covered_from"] == now

            concurrent_bucket = now + timedelta(minutes=10)
            connection.commit()
            start_together = Barrier(2)

            def replace_concurrently(event_count: int) -> None:
                with psycopg.connect(dsn) as concurrent_connection:
                    start_together.wait(timeout=10)
                    DashboardEventRollupRepository(concurrent_connection).replace_buckets(
                        bucket_keys=[(endpoint_id, concurrent_bucket)],
                        dimension_bucket_keys=[],
                        activity_rows=[
                            {
                                "bucket_start_at": concurrent_bucket,
                                "endpoint_id": endpoint_id,
                                "event_type": "DNS_QUERY",
                                "event_count": event_count,
                                "source_max_ingested_at": concurrent_bucket,
                            }
                        ],
                        dimension_rows=[],
                        refreshed_at=concurrent_bucket + timedelta(seconds=event_count),
                    )

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(replace_concurrently, count) for count in (4, 5)]
                for future in futures:
                    future.result(timeout=20)
            concurrent_rows = connection.execute(
                """
                SELECT count(*), max(event_count)
                FROM dashboard_event_rollups
                WHERE endpoint_id = %s AND bucket_start_at = %s AND event_type = 'DNS_QUERY'
                """,
                (endpoint_id, concurrent_bucket),
            ).fetchone()
            assert concurrent_rows[0] == 1
            assert concurrent_rows[1] in {4, 5}

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

            frozen_day = now - timedelta(days=10)
            metadata.upsert(
                IngestBucket(
                    endpoint_id,
                    frozen_day,
                    frozen_day + timedelta(days=1),
                    StorageBackend.CLICKHOUSE,
                    StorageClass.HOT,
                    StorageStatus.HOT,
                    f"clickhouse://edr_events/date={frozen_day.date().isoformat()}/endpoint_id={endpoint_id}",
                ),
                now,
            )
            connection.execute(
                """
                UPDATE ingest_metadata
                SET is_delete = TRUE, partition_deleted_at = %s
                WHERE endpoint_id = %s AND bucket_start_at = %s
                  AND storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT'
                """,
                (now, endpoint_id, frozen_day),
            )
            late_endpoint_id = EndpointRepository(connection).insert(
                EndpointInsert("agent-test-late-001", "TEST-LATE-ENDPOINT", OsType.MACOS, now)
            )
            with pytest.raises(ArchivedDayImmutableError):
                with metadata.hot_ingest_guard(
                    endpoint_id=late_endpoint_id,
                    occurred_at=frozen_day + timedelta(hours=1),
                    now=now,
                ):
                    pass
            assert (
                connection.execute(
                    """
                    SELECT count(*)
                    FROM ingest_metadata
                    WHERE endpoint_id = %s AND bucket_start_at = %s
                      AND storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT'
                    """,
                    (late_endpoint_id, frozen_day),
                ).fetchone()[0]
                == 0
            )
            assert DashboardEventRollupRepository(connection).frozen_bucket_dates(
                bucket_dates=[frozen_day.date()]
            ) == {frozen_day.date()}

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
            reopened = incidents.update_status_with_audit(
                incident_id=incident.incident_id,
                status=IncidentStatus.OPEN,
                actor_identifier="integration-test",
                request_id="req_incident_reopen",
                changed_at=now + timedelta(hours=1, minutes=1),
            )
            assert reopened["status"] == "OPEN"
            assert reopened["closed_at"] is None
            assert len(incidents.open_for_endpoint(endpoint_id)) == 1
            assert incidents.close_expired(now + timedelta(hours=2)) == 0
            closed = incidents.update_status_with_audit(
                incident_id=incident.incident_id,
                status=IncidentStatus.CLOSED,
                actor_identifier="integration-test",
                request_id="req_incident_close",
                changed_at=now + timedelta(hours=2, minutes=1),
            )
            assert closed["status"] == "CLOSED"
            assert closed["closed_at"] == now + timedelta(minutes=30)
            assert (
                connection.execute(
                    "SELECT count(*) FROM audit_logs WHERE action = 'INCIDENT_STATUS_CHANGED'"
                ).fetchone()[0]
                == 2
            )
        finally:
            apply_postgres_migrations(connection, ROOT / "migrations/postgresql", direction="down")


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
        repository = EventRepository.for_maintenance(client)
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
        activity_rows, dimension_rows = repository.dashboard_rollup_rows(
            from_=now,
            to=now + timedelta(minutes=1),
            endpoint_ids=[1001],
        )
        assert activity_rows == [
            {
                "endpoint_id": 1001,
                "bucket_start_at": now,
                "event_type": "DNS_QUERY",
                "event_count": 1,
                "source_max_ingested_at": now,
            }
        ]
        assert {
            (row["dimension_name"], row["dimension_value"], row["event_count"])
            for row in dimension_rows
        } == {("top_dns_queries", "example.com", 1)}

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


def test_clickhouse_to_postgres_dashboard_rollup_end_to_end() -> None:
    dsn = os.environ["TEST_POSTGRES_DSN"]
    client = clickhouse_connect.get_client(
        host=os.getenv("TEST_CLICKHOUSE_HOST", "127.0.0.1"),
        port=int(os.getenv("TEST_CLICKHOUSE_PORT", "58123")),
        username=os.getenv("TEST_CLICKHOUSE_USER", "edr"),
        password=os.environ["TEST_CLICKHOUSE_PASSWORD"],
        database=os.getenv("TEST_CLICKHOUSE_DATABASE", "edr"),
    )
    clickhouse_down = ROOT / "migrations/clickhouse/0001_initial.down.sql"
    clickhouse_up = ROOT / "migrations/clickhouse/0001_initial.up.sql"
    with psycopg.connect(dsn) as connection:
        apply_postgres_migrations(connection, ROOT / "migrations/postgresql", direction="down")
        apply_postgres_migrations(connection, ROOT / "migrations/postgresql")
        apply_clickhouse_file(client, clickhouse_down)
        apply_clickhouse_file(client, clickhouse_up)
        try:
            bucket_start = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
            endpoint_id = EndpointRepository(connection).insert(
                EndpointInsert("agent-rollup-001", "ROLLUP-ENDPOINT", OsType.MACOS, bucket_start)
            )
            connection.autocommit = True
            events = EventRepository.for_maintenance(client)
            first = _dns_event(
                101,
                bucket_start + timedelta(seconds=5),
                remote_domain="first.example",
                dns_answers="[]",
                endpoint_id=endpoint_id,
            )
            events.insert([first, first])
            rollups = DashboardEventRollupRepository(connection)
            synchronizer = DashboardRollupSynchronizer(events=events, store=rollups)

            synchronizer.refresh_range(from_=bucket_start, to=bucket_start + timedelta(minutes=1))
            first_summary = rollups.dashboard_summary(
                from_=bucket_start,
                to=bucket_start + timedelta(minutes=1),
                interval_seconds=60,
                endpoint_id=endpoint_id,
            )
            assert first_summary.total_count == 1
            assert first_summary.top_domains == {"first.example": 1}
            assert rollups.covers_range(
                from_=bucket_start + timedelta(seconds=5),
                to=bucket_start + timedelta(seconds=10),
            )
            with psycopg.connect(dsn) as observer_connection:
                observer_rollups = DashboardEventRollupRepository(observer_connection)
                assert observer_rollups.covers_range(from_=bucket_start, to=bucket_start + timedelta(minutes=1))
                assert observer_rollups.dashboard_summary(
                    from_=bucket_start,
                    to=bucket_start + timedelta(minutes=1),
                    interval_seconds=60,
                    endpoint_id=endpoint_id,
                ).total_count == 1

            second = _dns_event(
                102,
                bucket_start + timedelta(seconds=15),
                remote_domain="second.example",
                dns_answers="[]",
                endpoint_id=endpoint_id,
            )
            events.insert([second])
            synchronizer.refresh_range(from_=bucket_start, to=bucket_start + timedelta(minutes=1))
            second_summary = rollups.dashboard_summary(
                from_=bucket_start,
                to=bucket_start + timedelta(minutes=1),
                interval_seconds=60,
                endpoint_id=endpoint_id,
            )
            assert second_summary.total_count == 2
            assert second_summary.top_domains == {"first.example": 1, "second.example": 1}

            # The advisory guard must include both the ClickHouse read and the
            # PostgreSQL replacement. Otherwise a slow older read can overwrite
            # a newer result after the write-only lock is released.
            concurrent_bucket = bucket_start + timedelta(minutes=5)
            shared_count = {"value": 1}
            first_query_started = ThreadEvent()
            second_refresh_started = ThreadEvent()
            release_first_query = ThreadEvent()

            class SequencedEvents:
                def __init__(self, *, block_first: bool) -> None:
                    self.block_first = block_first

                def dashboard_rollup_rows(self, **_kwargs):
                    event_count = shared_count["value"]
                    if self.block_first:
                        first_query_started.set()
                        assert release_first_query.wait(timeout=10)
                    return ([{
                        "bucket_start_at": concurrent_bucket,
                        "endpoint_id": endpoint_id,
                        "event_type": "DNS_QUERY",
                        "event_count": event_count,
                        "source_max_ingested_at": concurrent_bucket,
                    }], [])

            def refresh_concurrently(*, block_first: bool) -> None:
                with psycopg.connect(dsn) as concurrent_connection:
                    if not block_first:
                        second_refresh_started.set()
                    DashboardRollupSynchronizer(
                        events=SequencedEvents(block_first=block_first),
                        store=DashboardEventRollupRepository(concurrent_connection),
                    ).refresh_range(
                        from_=concurrent_bucket,
                        to=concurrent_bucket + timedelta(minutes=1),
                        endpoint_ids=[endpoint_id],
                    )

            with ThreadPoolExecutor(max_workers=2) as executor:
                first_future = executor.submit(refresh_concurrently, block_first=True)
                assert first_query_started.wait(timeout=10)
                second_future = executor.submit(refresh_concurrently, block_first=False)
                assert second_refresh_started.wait(timeout=10)
                shared_count["value"] = 2
                release_first_query.set()
                first_future.result(timeout=20)
                second_future.result(timeout=20)

            serialized_count = connection.execute(
                """
                SELECT event_count
                FROM dashboard_event_rollups
                WHERE endpoint_id = %s AND bucket_start_at = %s AND event_type = 'DNS_QUERY'
                """,
                (endpoint_id, concurrent_bucket),
            ).fetchone()
            assert serialized_count == (2,)
        finally:
            apply_clickhouse_file(client, clickhouse_down)
            apply_postgres_migrations(connection, ROOT / "migrations/postgresql", direction="down")
            client.close()


def _dns_event(
    event_index: int, occurred_at: datetime, *, remote_domain: str, dns_answers: str, endpoint_id: int = 2001
) -> dict:
    unique = f"018ff8f4-86de-7b25-9b8a-2d22f6a3c{event_index:03d}"
    return {
        "event_id": UUID(unique),
        "batch_id": UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3c000"),
        "endpoint_id": endpoint_id,
        "agent_id": "agent-corr-001",
        "hostname": "CORR-ENDPOINT",
        "os_type": "MACOS",
        "ip_address": None,
        "event_type": "NETWORK_CONNECTION",
        "occurred_at": occurred_at,
        "ingested_at": occurred_at,
        "process_name": None,
        "process_path": None,
        "pid": None,
        "ppid": None,
        "command_line": None,
        "user_name": None,
        "file_path": None,
        "file_action": None,
        "file_hash_sha256": None,
        "remote_ip": "203.0.113.1",
        "remote_domain": remote_domain,
        "remote_port": 443,
        "protocol": "TCP",
        "dns_query": None,
        "dns_record_type": None,
        "dns_response_code": None,
        "dns_answers_json": dns_answers,
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
        "raw_payload": "{}",
        "payload_sha256": "0" * 64,
        "schema_version": 1,
        "created_at": occurred_at,
        "updated_at": occurred_at,
        "is_delete": 0,
    }


def test_event_search_domain_boundary_and_dns_answer_membership() -> None:
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
        window = (now, now + timedelta(seconds=1))
        repository = EventRepository.for_maintenance(client)
        repository.insert(
            [
                _dns_event(1, now, remote_domain="yahoo.com", dns_answers='["1.2.3.4"]'),
                _dns_event(2, now, remote_domain="mail.yahoo.com", dns_answers='["5.6.7.8"]'),
                _dns_event(3, now, remote_domain="finance.yahoo.com", dns_answers="[]"),
                _dns_event(4, now, remote_domain="notyahoo.com", dns_answers="[]"),
                _dns_event(5, now, remote_domain="yahoo.com.evil.example", dns_answers='["11.2.3.45"]'),
            ]
        )

        matched = {
            str(row["remote_domain"])
            for row in repository.search(from_=window[0], to=window[1], related_domain="yahoo.com")
        }
        assert matched == {"yahoo.com", "mail.yahoo.com", "finance.yahoo.com"}
        assert "notyahoo.com" not in matched
        assert "yahoo.com.evil.example" not in matched

        answer_hits = {
            str(row["remote_domain"])
            for row in repository.search(from_=window[0], to=window[1], dns_answer_ip="1.2.3.4")
        }
        # exact array-element membership: 1.2.3.4 must NOT match the event holding 11.2.3.45
        assert answer_hits == {"yahoo.com"}
    finally:
        apply_clickhouse_file(client, down)
        client.close()


def test_event_search_endpoint_ids_pushdown() -> None:
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
        window = (now, now + timedelta(seconds=1))
        repository = EventRepository.for_maintenance(client)
        repository.insert(
            [
                _dns_event(10, now, remote_domain="ep1.example.com", dns_answers="[]", endpoint_id=1),
                _dns_event(11, now, remote_domain="ep2.example.com", dns_answers="[]", endpoint_id=2),
            ]
        )
        scoped = {
            str(row["remote_domain"])
            for row in repository.search(
                from_=window[0], to=window[1], related_domain="example.com", endpoint_ids=[1]
            )
        }
        assert scoped == {"ep1.example.com"}
    finally:
        apply_clickhouse_file(client, down)
        client.close()
