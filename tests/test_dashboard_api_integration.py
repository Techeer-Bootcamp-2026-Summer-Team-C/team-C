import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import boto3
import clickhouse_connect
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from backend.auth import hash_password, issue_access_token
from backend.contracts.enums import UserRole
from backend.main import create_app
from backend.runtime import RuntimeServices
from backend.settings import Settings
from backend.storage.clickhouse import EventRepository
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_file
from backend.workers import normalize_event

ROOT = Path(__file__).parents[1]
RUN_INTEGRATION = os.getenv("EDR_RUN_DASHBOARD_INTEGRATION") == "1"
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not RUN_INTEGRATION, reason="dashboard integration disabled")]


class CapturingRestoreClient:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def restore(self, object_key: str) -> None:
        self.keys.append(object_key)


def _settings() -> Settings:
    return Settings(
        jwt_secret="dashboard-integration-jwt-secret-32-bytes-minimum",
        postgres_dsn=os.environ["TEST_POSTGRES_DSN"],
        clickhouse_dsn=(f"http://edr:{os.environ['TEST_CLICKHOUSE_PASSWORD']}@127.0.0.1:58123/edr"),
        kafka_bootstrap_servers=os.getenv("TEST_KAFKA_BOOTSTRAP", "127.0.0.1:59092"),
        s3_endpoint_url=os.getenv("TEST_S3_ENDPOINT", "http://127.0.0.1:59000"),
        s3_access_key_id=os.getenv("TEST_S3_ACCESS_KEY", "edr-local"),
        s3_secret_access_key=os.environ["TEST_S3_SECRET_KEY"],
        s3_bucket="edr-dashboard-integration",
        _env_file=None,
    )


def _raw_event(event_id: str, endpoint_id: int, agent_id: str, occurred_at: datetime, command: str) -> dict:
    rendered = occurred_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "schemaVersion": 1,
        "batchId": str(uuid4()),
        "endpointId": endpoint_id,
        "agentId": agent_id,
        "hostname": f"ENDPOINT-{endpoint_id}",
        "osType": "WINDOWS",
        "ipAddress": f"10.0.0.{endpoint_id}",
        "event": {
            "eventId": event_id,
            "eventType": "PROCESS_EXECUTION",
            "occurredAt": rendered,
            "payload": {"processName": "powershell.exe", "pid": endpoint_id, "commandLine": command},
        },
    }


def _parquet_row(record: dict) -> dict:
    row = dict(record)
    row["event_id"] = str(row["event_id"])
    row["batch_id"] = str(row["batch_id"])
    return row


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_api_auth_hot_restored_archive_and_empty_contracts() -> None:
    settings = _settings()
    postgres_dsn = settings.postgres_dsn.get_secret_value()
    clickhouse = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=58123,
        username="edr",
        password=os.environ["TEST_CLICKHOUSE_PASSWORD"],
        database="edr",
    )
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name="us-east-1",
    )
    postgres_down = ROOT / "migrations/postgresql/0001_initial.down.sql"
    postgres_up = ROOT / "migrations/postgresql/0001_initial.up.sql"
    postgres_login_id_up = ROOT / "migrations/postgresql/0002_user_login_id.up.sql"
    clickhouse_down = ROOT / "migrations/clickhouse/0001_initial.down.sql"
    clickhouse_up = ROOT / "migrations/clickhouse/0001_initial.up.sql"
    with psycopg.connect(postgres_dsn) as connection:
        apply_postgres_file(connection, postgres_down)
        apply_postgres_file(connection, postgres_up)
        apply_postgres_file(connection, postgres_login_id_up)
    apply_clickhouse_file(clickhouse, clickhouse_down)
    apply_clickhouse_file(clickhouse, clickhouse_up)
    try:
        s3.create_bucket(Bucket=settings.s3_bucket)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass

    now = datetime.now(UTC).replace(microsecond=0)
    current_day = now.replace(hour=0, minute=0, second=0)
    old_day = current_day - timedelta(days=30)
    hot_event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3a001")
    restored_event_id = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3a002")
    hot_record = normalize_event(
        _raw_event(str(hot_event_id), 1, "agent-hot", now - timedelta(minutes=2), "powershell -EncodedCommand QQ=="),
        ingested_at=now - timedelta(minutes=1),
    )
    restored_record = normalize_event(
        _raw_event(str(restored_event_id), 2, "agent-restored", now - timedelta(minutes=1), "notepad.exe"),
        ingested_at=now,
    )
    EventRepository(clickhouse).insert([hot_record])

    with psycopg.connect(postgres_dsn) as connection:
        admin_hash = hash_password("admin-password")
        viewer_hash = hash_password("viewer-password")
        disabled_hash = hash_password("disabled-password")
        connection.execute(
            """
            INSERT INTO users (login_id, password_hash, name, role, status, created_at, updated_at) VALUES
            ('admin', %s, 'Admin', 'ADMIN', 'ACTIVE', %s, %s),
            ('viewer', %s, 'Viewer', 'VIEWER', 'ACTIVE', %s, %s),
            ('disabled', %s, 'Disabled', 'ANALYST', 'DISABLED', %s, %s)
            """,
            (admin_hash, now, now, viewer_hash, now, now, disabled_hash, now, now),
        )
        connection.execute(
            """
            INSERT INTO endpoints (
                endpoint_id, agent_id, hostname, os_type, capability_codes_json, sensor_health_json,
                registered_at, status, last_seen_at, created_at, updated_at
            ) VALUES
            (1, 'agent-hot', 'ENDPOINT-1', 'WINDOWS', '["PROCESS_EXECUTION"]',
             '[{"sensor":"PROCESS","status":"HEALTHY"}]', %s, 'ONLINE', %s, %s, %s),
            (2, 'agent-restored', 'ENDPOINT-2', 'WINDOWS', '[]', '[]', %s, 'OFFLINE', %s, %s, %s),
            (3, 'agent-archive', 'ENDPOINT-3', 'MACOS', '[]', '[]', %s, 'RETIRED', %s, %s, %s)
            """,
            (
                now - timedelta(days=10),
                now,
                now,
                now,
                now - timedelta(days=10),
                now - timedelta(days=8),
                now,
                now,
                now - timedelta(days=40),
                now - timedelta(days=30),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO ingest_metadata (
                endpoint_id, bucket_start_at, bucket_end_at, storage_backend, storage_class,
                storage_status, storage_path, event_count, created_at, updated_at
            ) VALUES
            (1, %s, %s, 'CLICKHOUSE', 'HOT', 'HOT', %s, 1, %s, %s),
            (2, %s, %s, 'S3', 'GLACIER_FLEXIBLE_RETRIEVAL', 'RESTORED', %s, 1, %s, %s),
            (3, %s, %s, 'S3', 'GLACIER_FLEXIBLE_RETRIEVAL', 'ARCHIVED', %s, 0, %s, %s)
            """,
            (
                current_day,
                current_day + timedelta(days=1),
                "clickhouse://edr_events/date=current/endpoint_id=1",
                now,
                now,
                current_day,
                current_day + timedelta(days=1),
                "archives/restored-endpoint-2.parquet",
                now,
                now,
                old_day,
                old_day + timedelta(days=1),
                "archives/endpoint-3.parquet",
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
            ) VALUES (
                1, 1, %s, %s, %s, 'agent-hot', 'PROC_POWERSHELL_ENCODED',
                'PowerShell Encoded Command', 1, 'TA0002', 'Execution', 'T1059.001', 'PowerShell',
                'Encoded PowerShell command detected',
                'PowerShell was executed with an encoded command argument.',
                'HIGH', 85, 'OPEN', %s, %s, %s
            )
            """,
            (hot_event_id, hot_record["occurred_at"], hot_record["batch_id"], now, now, now),
        )
        connection.execute(
            """
            INSERT INTO incidents (
                incident_id, endpoint_id, correlation_key, window_start_at, window_end_at,
                title, description, severity, status, first_detected_at, last_detected_at,
                closed_at, created_at, updated_at
            ) VALUES (1, 1, 'suspicious-powershell', %s, %s,
                'Encoded PowerShell command detected',
                'PowerShell was executed with an encoded command argument.',
                'HIGH', 'OPEN', %s, %s, NULL, %s, %s)
            """,
            (current_day, current_day + timedelta(days=1), now, now, now, now),
        )
        connection.execute(
            """
            INSERT INTO incident_alerts (incident_id, alert_id, linked_at, created_at, updated_at)
            VALUES (1, 1, %s, %s, %s)
            """,
            (now, now, now),
        )
        connection.commit()

    runtime = RuntimeServices(settings)
    pq.write_table(
        pa.Table.from_pylist([_parquet_row(restored_record)]),
        f"{settings.s3_bucket}/archives/restored-endpoint-2.parquet",
        filesystem=runtime.restored_events.filesystem,
    )
    restore_client = CapturingRestoreClient()
    runtime.restore_client = restore_client
    client = TestClient(create_app(runtime))
    try:
        login = client.post(
            "/api/v1/auth/login",
            json={"loginId": " ADMIN ", "password": "admin-password"},
        )
        assert login.status_code == 200
        admin_token = login.json()["data"]["accessToken"]
        assert login.json()["data"]["expiresIn"] == 43_200
        assert login.json()["data"]["user"]["loginId"] == "admin"
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"loginId": "admin", "password": "wrong"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"loginId": "disabled", "password": "disabled-password"},
            ).status_code
            == 403
        )
        viewer_token = client.post(
            "/api/v1/auth/login",
            json={"loginId": "viewer", "password": "viewer-password"},
        ).json()["data"]["accessToken"]
        tampered = admin_token + "tampered"
        expired = issue_access_token(
            user_id=1,
            role=UserRole.ADMIN,
            secret="dashboard-integration-jwt-secret-32-bytes-minimum",
            now=datetime.now(UTC) - timedelta(hours=13),
        )
        assert client.get("/api/v1/endpoints", headers=_auth(tampered)).status_code == 401
        assert client.get("/api/v1/endpoints", headers=_auth(expired)).status_code == 401

        endpoint_list = client.get(
            "/api/v1/endpoints",
            headers=_auth(admin_token),
            params={"page": 1, "size": 2, "sortBy": "riskScore", "sortOrder": "desc"},
        )
        assert endpoint_list.status_code == 200
        assert endpoint_list.json()["data"]["items"][0]["risk"]["score"] >= 85
        assert client.get("/api/v1/endpoints/1", headers=_auth(admin_token)).status_code == 200
        assert client.get("/api/v1/endpoints/999", headers=_auth(admin_token)).status_code == 404

        range_params = {
            "timePreset": "CUSTOM",
            "from": (current_day).isoformat().replace("+00:00", "Z"),
            "to": (current_day + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "sortOrder": "asc",
        }
        merged = client.get(
            "/api/v1/events",
            headers=_auth(admin_token),
            params={**range_params, "page": 1, "size": 1},
        )
        merged_page_2 = client.get(
            "/api/v1/events",
            headers=_auth(admin_token),
            params={**range_params, "page": 2, "size": 1},
        )
        assert merged.status_code == 200
        assert merged.json()["data"]["total"] == 2
        assert merged_page_2.json()["data"]["items"]
        hot_detail = client.get(
            f"/api/v1/events/{hot_event_id}",
            headers=_auth(admin_token),
            params={"endpointId": 1, "occurredAt": hot_record["occurred_at"].isoformat().replace("+00:00", "Z")},
        )
        restored_detail = client.get(
            f"/api/v1/events/{restored_event_id}",
            headers=_auth(admin_token),
            params={
                "endpointId": 2,
                "occurredAt": restored_record["occurred_at"].isoformat().replace("+00:00", "Z"),
            },
        )
        assert hot_detail.status_code == 200
        assert restored_detail.status_code == 200
        assert restored_detail.json()["data"]["eventId"] == str(restored_event_id)
        assert (
            client.get(
                "/api/v1/events",
                headers=_auth(admin_token),
                params={"timePreset": "CUSTOM"},
            ).status_code
            == 400
        )

        assert client.get("/api/v1/alerts", headers=_auth(admin_token)).status_code == 200
        alert_detail = client.get("/api/v1/alerts/1", headers=_auth(admin_token))
        assert alert_detail.status_code == 200
        assert [item["order"] for item in alert_detail.json()["data"]["responseGuidance"]] == [1]
        assert client.get("/api/v1/incidents", headers=_auth(admin_token)).status_code == 200
        assert client.get("/api/v1/incidents/1", headers=_auth(admin_token)).status_code == 200
        assert client.patch("/api/v1/incidents/1", headers=_auth(admin_token), json={}).status_code == 405

        assert (
            client.patch(
                "/api/v1/alerts/1/status",
                headers=_auth(viewer_token),
                json={"status": "RESOLVED"},
            ).status_code
            == 403
        )
        changed = client.patch(
            "/api/v1/alerts/1/status",
            headers=_auth(admin_token),
            json={"status": "IN_PROGRESS"},
        )
        same_state = client.patch(
            "/api/v1/alerts/1/status",
            headers=_auth(admin_token),
            json={"status": "IN_PROGRESS"},
        )
        assert changed.status_code == same_state.status_code == 200
        with psycopg.connect(postgres_dsn) as connection:
            assert (
                connection.execute("SELECT count(*) FROM audit_logs WHERE action = 'ALERT_STATUS_CHANGED'").fetchone()[
                    0
                ]
                == 1
            )

        dashboard_paths = (
            "/api/v1/dashboard/summary?timePreset=LATEST_24H&interval=5m",
            "/api/v1/dashboard/endpoints/summary?timePreset=LATEST_24H",
            "/api/v1/dashboard/ingest/summary?timePreset=LATEST_24H",
        )
        with ThreadPoolExecutor(max_workers=3) as executor:
            parallel_responses = list(
                executor.map(lambda path: client.get(path, headers=_auth(admin_token)), dashboard_paths)
            )
        assert [response.status_code for response in parallel_responses] == [200, 200, 200]

        for path in dashboard_paths:
            response = client.get(path, headers=_auth(admin_token))
            assert response.status_code == 200, response.text

        restored_restore = client.post(
            "/api/v1/archives/restores",
            headers=_auth(admin_token),
            json={
                "endpointIds": [2],
                "from": current_day.isoformat().replace("+00:00", "Z"),
                "to": (current_day + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            },
        )
        assert restored_restore.status_code == 200
        assert restore_client.keys == []
        old_request = {
            "endpointIds": [3],
            "from": old_day.isoformat().replace("+00:00", "Z"),
            "to": (old_day + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        }
        assert (
            client.post("/api/v1/archives/restores", headers=_auth(viewer_token), json=old_request).status_code == 403
        )
        requested = client.post("/api/v1/archives/restores", headers=_auth(admin_token), json=old_request)
        assert requested.status_code == 202
        assert restore_client.keys == ["archives/endpoint-3.parquet"]
        in_progress = client.post("/api/v1/archives/restores", headers=_auth(admin_token), json=old_request)
        assert in_progress.status_code == 202
        assert restore_client.keys == ["archives/endpoint-3.parquet"]
        archive_list = client.get(
            "/api/v1/archives/restores",
            headers=_auth(admin_token),
            params=[
                ("endpointIds", "3"),
                ("from", old_request["from"]),
                ("to", old_request["to"]),
                ("page", "1"),
                ("size", "50"),
            ],
        )
        assert archive_list.status_code == 200
        not_ready = client.get(
            "/api/v1/events",
            headers=_auth(admin_token),
            params={
                "endpointId": 3,
                "timePreset": "CUSTOM",
                "from": old_request["from"],
                "to": old_request["to"],
            },
        )
        assert not_ready.status_code == 409
        assert not_ready.json()["error"]["code"] == "ARCHIVE_NOT_READY"

        with psycopg.connect(postgres_dsn) as connection:
            connection.execute("DELETE FROM incident_alerts")
            connection.execute("DELETE FROM incidents")
            connection.execute("DELETE FROM alerts")
            connection.execute("DELETE FROM agent_auth_keys")
            connection.execute("DELETE FROM ingest_metadata")
            connection.execute("DELETE FROM endpoints")
            connection.commit()
        clickhouse.command("TRUNCATE TABLE edr_events")
        empty_dashboard = client.get(
            "/api/v1/dashboard/summary?timePreset=LATEST_24H&interval=5m",
            headers=_auth(admin_token),
        ).json()["data"]
        empty_endpoints = client.get(
            "/api/v1/dashboard/endpoints/summary?timePreset=LATEST_24H",
            headers=_auth(admin_token),
        ).json()["data"]
        empty_ingest = client.get(
            "/api/v1/dashboard/ingest/summary?timePreset=LATEST_24H",
            headers=_auth(admin_token),
        ).json()["data"]
        assert empty_dashboard["events"]["totalCount"] == 0
        assert empty_dashboard["alerts"]["bySeverity"] == []
        assert empty_endpoints["risk"]["highestScore"] is None
        assert empty_ingest["events"] == {"ingestedCount": 0, "latestIngestedAt": None}
    finally:
        with psycopg.connect(postgres_dsn) as connection:
            apply_postgres_file(connection, postgres_down)
        apply_clickhouse_file(clickhouse, clickhouse_down)
        for item in s3.list_objects_v2(Bucket=settings.s3_bucket).get("Contents", []):
            s3.delete_object(Bucket=settings.s3_bucket, Key=item["Key"])
        s3.delete_bucket(Bucket=settings.s3_bucket)
        clickhouse.close()
