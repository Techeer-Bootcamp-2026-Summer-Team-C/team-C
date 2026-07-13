"""브라우저 QA용 실제 로컬 서비스를 초기화한다. 운영 코드에서는 import하지 않는다."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import boto3
import clickhouse_connect
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq

from backend.auth import hash_password
from backend.event_service import RestoredEventReader
from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_file
from backend.workers import normalize_event

ROOT = Path(__file__).parents[1]
POSTGRES_DSN = os.getenv(
    "EDR_POSTGRES_DSN",
    "postgresql://edr:replace-with-a-local-password@127.0.0.1:55432/edr",
)
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "replace-with-a-local-password")
S3_ENDPOINT = os.getenv("EDR_S3_ENDPOINT_URL", "http://127.0.0.1:59000")
S3_ACCESS_KEY = os.getenv("EDR_S3_ACCESS_KEY_ID", "edr-local")
S3_SECRET_KEY = os.getenv("EDR_S3_SECRET_ACCESS_KEY", "replace-with-a-local-password")
S3_BUCKET = os.getenv("EDR_S3_BUCKET", "edr-failures")


def raw_event(
    *,
    event_id: str,
    event_type: str,
    payload: dict,
    endpoint_id: int = 1,
    agent_id: str = "agent-soc-001",
    occurred_at: datetime,
) -> dict:
    return {
        "schemaVersion": 1,
        "batchId": str(uuid4()),
        "endpointId": endpoint_id,
        "agentId": agent_id,
        "hostname": "SOC-WIN-01" if endpoint_id == 1 else "FINANCE-MAC-02",
        "osType": "WINDOWS" if endpoint_id == 1 else "MACOS",
        "ipAddress": f"10.24.0.{endpoint_id}",
        "event": {
            "eventId": event_id,
            "eventType": event_type,
            "occurredAt": occurred_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "payload": payload,
        },
    }


def main() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    day = now.replace(hour=0, minute=0, second=0)
    old_day = day - timedelta(days=30)
    clickhouse = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=58123,
        username="edr",
        password=CLICKHOUSE_PASSWORD,
        database="edr",
    )
    with psycopg.connect(POSTGRES_DSN) as connection:
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0002_refresh_sessions.down.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0001_initial.down.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0001_initial.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0002_refresh_sessions.up.sql")
    apply_clickhouse_file(clickhouse, ROOT / "migrations/clickhouse/0001_initial.down.sql")
    apply_clickhouse_file(clickhouse, ROOT / "migrations/clickhouse/0001_initial.up.sql")

    events = [
        normalize_event(
            raw_event(
                event_id="018ff8f4-86de-7b25-9b8a-2d22f6c10001",
                event_type="PROCESS_EXECUTION",
                payload={
                    "processName": "powershell.exe",
                    "processPath": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                    "pid": 4242,
                    "ppid": 900,
                    "commandLine": "powershell -EncodedCommand SQBFAFgA",
                    "userName": "SOC\\analyst.service",
                },
                occurred_at=now - timedelta(minutes=18),
            ),
            ingested_at=now - timedelta(minutes=17),
        ),
        normalize_event(
            raw_event(
                event_id="018ff8f4-86de-7b25-9b8a-2d22f6c10002",
                event_type="NETWORK_CONNECTION",
                payload={
                    "protocol": "TCP",
                    "remoteIp": "203.0.113.88",
                    "remotePort": 443,
                    "remoteDomain": "update-cache.example.net",
                    "processName": "powershell.exe",
                    "pid": 4242,
                },
                occurred_at=now - timedelta(minutes=15),
            ),
            ingested_at=now - timedelta(minutes=14),
        ),
        normalize_event(
            raw_event(
                event_id="018ff8f4-86de-7b25-9b8a-2d22f6c10003",
                event_type="FILE_EVENT",
                payload={
                    "filePath": "C:\\ProgramData\\cache\\payload-with-an-intentionally-long-security-artifact-name.bin",
                    "action": "CREATE",
                    "sha256": "a" * 64,
                    "processName": "powershell.exe",
                    "pid": 4242,
                },
                occurred_at=now - timedelta(minutes=12),
            ),
            ingested_at=now - timedelta(minutes=11),
        ),
        normalize_event(
            raw_event(
                event_id="018ff8f4-86de-7b25-9b8a-2d22f6c10004",
                event_type="DNS_QUERY",
                payload={
                    "query": "update-cache.example.net",
                    "recordType": "A",
                    "responseCode": "NOERROR",
                    "answers": ["203.0.113.88"],
                    "processName": "powershell.exe",
                    "pid": 4242,
                },
                occurred_at=now - timedelta(minutes=9),
            ),
            ingested_at=now - timedelta(minutes=8),
        ),
        normalize_event(
            raw_event(
                event_id="018ff8f4-86de-7b25-9b8a-2d22f6c10005",
                event_type="L7_EVENT",
                payload={
                    "l7Protocol": "HTTPS",
                    "httpMethod": "POST",
                    "httpHost": "update-cache.example.net",
                    "url": "https://update-cache.example.net/telemetry/upload/long-path-segment",
                    "httpStatusCode": 202,
                    "httpUserAgent": "PowerShell/7.5",
                    "tlsSni": "update-cache.example.net",
                    "tlsVersion": "TLS1.3",
                    "tlsCertificateSubject": "CN=update-cache.example.net",
                    "tlsCertificateIssuer": "CN=Example Test CA",
                    "tlsCertificateSha256": "b" * 64,
                },
                occurred_at=now - timedelta(minutes=6),
            ),
            ingested_at=now - timedelta(minutes=5),
        ),
    ]
    restored = normalize_event(
        raw_event(
            event_id="018ff8f4-86de-7b25-9b8a-2d22f6c20001",
            event_type="PROCESS_EXECUTION",
            payload={"processName": "launchctl", "processPath": "/bin/launchctl", "pid": 812},
            endpoint_id=2,
            agent_id="agent-finance-mac-002",
            occurred_at=now - timedelta(minutes=4),
        ),
        ingested_at=now - timedelta(minutes=3),
    )
    EventRepository(clickhouse).insert(events)
    FailureRepository(clickhouse).insert(
        [
            {
                "failure_id": UUID("018ff8f4-86de-7b25-9b8a-2d22f6cf0001"),
                "event_id": UUID("018ff8f4-86de-7b25-9b8a-2d22f6c10005"),
                "endpoint_id": 1,
                "source_topic": "telemetry.raw",
                "source_partition": 0,
                "source_offset": 21,
                "consumer_name": "event-storage-worker",
                "failure_stage": "EVENT_STORAGE",
                "failure_code": "S3_WRITE_FAILED",
                "error_message": "QA fixture transient storage failure",
                "retryable": 1,
                "retry_count": 3,
                "payload_object_key": "failures/qa-fixture.json.gz",
                "payload_sha256": "c" * 64,
                "payload_size_bytes": 128,
                "status": "FAILED",
                "failed_at": now - timedelta(minutes=20),
                "replay_count": 0,
                "last_replayed_at": None,
                "reprocess_outcome": None,
                "resolved_at": None,
                "retention_expires_at": now + timedelta(days=97),
                "created_at": now - timedelta(minutes=20),
                "updated_at": now - timedelta(minutes=20),
            }
        ]
    )

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )
    try:
        s3.create_bucket(Bucket=S3_BUCKET)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    reader = RestoredEventReader(
        endpoint_url=S3_ENDPOINT,
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
        bucket=S3_BUCKET,
    )
    restored_row = dict(restored)
    restored_row["event_id"] = str(restored_row["event_id"])
    restored_row["batch_id"] = str(restored_row["batch_id"])
    pq.write_table(
        pa.Table.from_pylist([restored_row]),
        f"{S3_BUCKET}/archives/finance-mac-restored.parquet",
        filesystem=reader.filesystem,
    )

    admin_hash = hash_password("frontend-admin-password")
    viewer_hash = hash_password("frontend-viewer-password")
    disabled_hash = hash_password("frontend-disabled-password")
    with psycopg.connect(POSTGRES_DSN) as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, email, password_hash, name, role, status, created_at, updated_at) VALUES
            (1, 'frontend-admin@example.com', %s, 'SOC Administrator', 'ADMIN', 'ACTIVE', %s, %s),
            (2, 'frontend-viewer@example.com', %s, 'Read-only Reviewer', 'VIEWER', 'ACTIVE', %s, %s),
            (3, 'frontend-disabled@example.com', %s, 'Disabled Analyst', 'ANALYST', 'DISABLED', %s, %s)
            """,
            (admin_hash, now, now, viewer_hash, now, now, disabled_hash, now, now),
        )
        connection.execute(
            """
            INSERT INTO endpoints (
                endpoint_id, agent_id, hostname, os_type, os_version, ip_address, agent_version,
                agent_build_id, agent_arch, capability_codes_json, sensor_health_json,
                registered_at, status, last_seen_at, created_at, updated_at
            ) VALUES
            (1, 'agent-soc-001', 'SOC-WIN-01', 'WINDOWS', 'Windows 11 24H2', '10.24.0.1', '2.7.1',
             'win-x64-20260712.1', 'X64',
             '["PROCESS_EXECUTION","NETWORK_CONNECTION","FILE_EVENT","DNS_QUERY","L7_EVENT"]',
             '[{"sensor":"PROCESS","status":"HEALTHY","provider":"ETW","packetDropCount":0,"parseErrorCount":0},{"sensor":"NETWORK","status":"DEGRADED","provider":"WFP","packetDropCount":12,"parseErrorCount":1}]',
             %s, 'ONLINE', %s, %s, %s),
            (2, 'agent-finance-mac-002', 'FINANCE-MAC-02', 'MACOS', 'macOS 15.5', '10.24.0.2', '2.7.0',
             'mac-arm64-20260701.4', 'ARM64', '["PROCESS_EXECUTION"]',
             '[{"sensor":"PROCESS","status":"HEALTHY","provider":"EndpointSecurity","packetDropCount":0,"parseErrorCount":0}]',
             %s, 'OFFLINE', %s, %s, %s),
            (3, 'agent-retired-lab-003', 'RETIRED-LAB-ENDPOINT-WITH-A-LONG-HOSTNAME-003', 'WINDOWS', NULL, NULL, NULL,
             NULL, NULL, '[]', '[]', %s, 'RETIRED', %s, %s, %s)
            """,
            (
                now - timedelta(days=40),
                now - timedelta(minutes=1),
                now,
                now,
                now - timedelta(days=75),
                now - timedelta(days=8),
                now,
                now,
                now - timedelta(days=180),
                now - timedelta(days=30),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO agent_auth_keys (
                endpoint_id, cert_fingerprint, cert_subject, cert_san_agent_id,
                issued_at, expires_at, revoked_at, created_at, updated_at
            ) VALUES
            (1, %s, 'CN=agent-soc-001,O=EDR QA', 'agent-soc-001', %s, %s, NULL, %s, %s)
            """,
            ("d" * 64, now - timedelta(days=10), now + timedelta(days=355), now, now),
        )
        connection.execute(
            """
            INSERT INTO ingest_metadata (
                endpoint_id, bucket_start_at, bucket_end_at, storage_backend, storage_class,
                storage_status, storage_path, event_count, size_bytes, checksum_sha256,
                archived_at, archive_verified_at, restore_requested_at, restored_at, restore_expires_at,
                last_error, created_at, updated_at
            ) VALUES
            (1, %s, %s, 'CLICKHOUSE', 'HOT', 'HOT', %s, 5, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, %s, %s),
            (2, %s, %s, 'S3', 'GLACIER_FLEXIBLE_RETRIEVAL', 'RESTORED',
             %s, 1, 2048, %s, %s, %s, %s, %s, %s, NULL, %s, %s),
            (3, %s, %s, 'S3', 'GLACIER_FLEXIBLE_RETRIEVAL', 'ARCHIVED',
             %s, 42, 8192, %s, %s, %s, NULL, NULL, NULL, NULL, %s, %s)
            """,
            (
                day,
                day + timedelta(days=1),
                "clickhouse://edr_events/date=current/endpoint_id=1",
                now,
                now,
                day,
                day + timedelta(days=1),
                "archives/finance-mac-restored.parquet",
                "e" * 64,
                now - timedelta(days=30),
                now - timedelta(days=23),
                now - timedelta(hours=1),
                now - timedelta(minutes=45),
                now + timedelta(days=6),
                now,
                now,
                old_day,
                old_day + timedelta(days=1),
                "archives/retired-lab-003-with-a-very-long-object-key.parquet",
                "f" * 64,
                now - timedelta(days=29),
                now - timedelta(days=22),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO alerts (
                alert_id, endpoint_id, event_id, event_occurred_at, batch_id, agent_id,
                rule_code, rule_name, rule_version, mitre_tactic_code, mitre_tactic_name,
                mitre_technique_code, mitre_technique_name, title, summary, severity,
                risk_score, status, detected_at, created_at, updated_at
            ) VALUES
            (1, 1, %s, %s, %s, 'agent-soc-001', 'PROC_POWERSHELL_ENCODED', 'PowerShell Encoded Command', 1,
             'TA0002', 'Execution', 'T1059.001', 'PowerShell', 'Encoded PowerShell command detected',
             'PowerShell was executed with an encoded command argument.', 'HIGH', 85, 'OPEN', %s, %s, %s),
            (2, 1, %s, %s, %s, 'agent-soc-001', 'NET_SUSPICIOUS_EGRESS', 'Suspicious Egress Destination', 1,
             'TA0011', 'Command and Control', 'T1071.001', 'Web Protocols', 'Suspicious encrypted egress detected',
             'A monitored process connected to a rare external destination.', 'CRITICAL', 92, 'IN_PROGRESS', %s, %s, %s)
            """,
            (
                events[0]["event_id"],
                events[0]["occurred_at"],
                events[0]["batch_id"],
                now - timedelta(minutes=17),
                now,
                now,
                events[1]["event_id"],
                events[1]["occurred_at"],
                events[1]["batch_id"],
                now - timedelta(minutes=14),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO incidents (
                incident_id, endpoint_id, correlation_key, window_start_at, window_end_at,
                title, description, severity, status, first_detected_at, last_detected_at,
                closed_at, created_at, updated_at
            ) VALUES
            (1, 1, 'suspicious-powershell', %s, %s, 'Encoded PowerShell command detected',
             'PowerShell was executed with an encoded command argument.', 'HIGH', 'OPEN', %s, %s, NULL, %s, %s)
            """,
            (day, day + timedelta(days=1), now - timedelta(minutes=18), now - timedelta(minutes=14), now, now),
        )
        connection.execute(
            """
            INSERT INTO incident_alerts (incident_id, alert_id, linked_at, created_at, updated_at) VALUES
            (1, 1, %s, %s, %s), (1, 2, %s, %s, %s)
            """,
            (now, now, now, now, now, now),
        )
        connection.commit()
    clickhouse.close()
    print("Browser QA fixture seeded")
    print("ADMIN frontend-admin@example.com / frontend-admin-password")
    print("VIEWER frontend-viewer@example.com / frontend-viewer-password")
    old_day_end = old_day + timedelta(days=1)
    print(f"ARCHIVE_NOT_READY range: endpointId=3 from={old_day.isoformat()} to={old_day_end.isoformat()}")


if __name__ == "__main__":
    main()
