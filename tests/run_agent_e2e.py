from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import boto3
import clickhouse_connect
import psycopg
import uvicorn
from botocore.exceptions import ClientError
from confluent_kafka.admin import AdminClient

from backend.auth import hash_password
from backend.detection import DetectionEngine
from backend.failure import FailureSink
from backend.kafka import RAW_TOPIC, TOPICS, VALIDATED_TOPIC, KafkaConsumer, ensure_topics
from backend.main import create_app
from backend.runtime import RuntimeServices
from backend.settings import Settings
from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_file
from backend.storage.postgres import AlertRepository, IncidentRepository, IngestMetadataRepository
from backend.workers import DetectionWorker, EventStorageWorker
from tools.provision_agent_cert import provision

ROOT = Path(__file__).parents[1]


def run(*arguments: str) -> None:
    subprocess.run(arguments, check=True, capture_output=True)


def certificate_sha1(path: Path) -> str:
    result = subprocess.run(
        ["openssl", "x509", "-in", str(path), "-noout", "-fingerprint", "-sha1"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().split("=", 1)[1]


def start_nginx(
    directory: Path,
    *,
    certificate: Path,
    private_key: Path,
    client_ca: Path,
    agent_certificate: Path,
    agent_id: str,
    fingerprint_sha256: str,
) -> str:
    sha1 = certificate_sha1(agent_certificate)
    sha1_without_colons = sha1.replace(":", "")
    container_certificate = Path("/agent-e2e") / certificate.relative_to(directory)
    container_private_key = Path("/agent-e2e") / private_key.relative_to(directory)
    container_client_ca = Path("/agent-e2e") / client_ca.relative_to(directory)
    config = directory / "nginx.conf"
    config.write_text(
        "events {}\n"
        "http {\n"
        "  map_hash_bucket_size 128;\n"
        "  map $ssl_client_fingerprint $edr_ssl_client_san_agent_id {\n"
        '    default "";\n'
        f'    "{sha1}" "{agent_id}";\n'
        f'    "{sha1_without_colons}" "{agent_id}";\n'
        "  }\n"
        "  map $ssl_client_fingerprint $edr_ssl_client_fingerprint_sha256 {\n"
        '    default "";\n'
        f'    "{sha1}" "{fingerprint_sha256}";\n'
        f'    "{sha1_without_colons}" "{fingerprint_sha256}";\n'
        "  }\n"
        "  log_format mtls '$ssl_client_verify|$ssl_client_fingerprint|$ssl_client_s_dn|"
        "$ssl_client_v_start|$ssl_client_v_end|$http_x_edr_certificate_san_agent_id';\n"
        "  access_log /var/log/nginx/access.log mtls;\n"
        "  server {\n"
        "    listen 8443 ssl;\n"
        f"    ssl_certificate {container_certificate};\n"
        f"    ssl_certificate_key {container_private_key};\n"
        f"    ssl_client_certificate {container_client_ca};\n"
        "    ssl_verify_client on;\n"
        "    ssl_verify_depth 1;\n"
        "    ssl_protocols TLSv1.2 TLSv1.3;\n"
        "    client_max_body_size 2m;\n"
        "    location /api/v1/collector/ {\n"
        "      proxy_pass http://host.docker.internal:58877;\n"
        "      proxy_http_version 1.1;\n"
        "      proxy_set_header Host $host;\n"
        "      include /etc/nginx/snippets/collector_trusted_headers.conf;\n"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    name = f"edr-agent-e2e-nginx-{os.getpid()}"
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--detach",
            "--name",
            name,
            "--publish",
            "58443:8443",
            "--volume",
            f"{directory}:/agent-e2e:ro",
            "--volume",
            f"{ROOT / 'deploy/nginx'}:/etc/nginx/snippets:ro",
            "nginx:alpine",
            "nginx",
            "-g",
            "daemon off;",
            "-c",
            "/agent-e2e/nginx.conf",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 58443), timeout=0.5):
                time.sleep(1)
                return name
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Nginx did not start listening")


def mtls_request_json(
    url: str,
    *,
    body: dict,
    certificate: Path,
    private_key: Path,
    ca_certificate: Path,
    spoof_identity_headers: bool = False,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if spoof_identity_headers:
        headers.update(
            {
                "X-EDR-mTLS-Verify": "FAILED",
                "X-EDR-Certificate-Subject": "CN=external-spoof",
                "X-EDR-Certificate-SAN-Agent-ID": "external-spoof",
                "X-EDR-Certificate-Fingerprint-SHA256": "0" * 64,
                "X-EDR-Certificate-Not-Before": "Jan 01 00:00:00 1970 GMT",
                "X-EDR-Certificate-Not-After": "Jan 01 00:00:00 1971 GMT",
            }
        )
    request = urllib.request.Request(url, method="POST", headers=headers, data=json.dumps(body).encode("utf-8"))
    context = ssl.create_default_context(cafile=str(ca_certificate))
    context.load_cert_chain(certificate, private_key)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    with opener.open(request, timeout=20) as response:
        return response.status, json.loads(response.read())


def create_server_certificate(directory: Path, ca_certificate: Path, ca_key: Path) -> tuple[Path, Path]:
    key = directory / "server.key"
    csr = directory / "server.csr"
    certificate = directory / "server.crt"
    extensions = directory / "server-extensions.cnf"
    extensions.write_text(
        "[server]\nbasicConstraints=critical,CA:FALSE\nsubjectAltName=IP:127.0.0.1\n"
        "extendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\n",
        encoding="utf-8",
    )
    run(
        "openssl",
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=127.0.0.1",
        "-addext",
        "subjectAltName=IP:127.0.0.1",
        "-addext",
        "extendedKeyUsage=serverAuth",
        "-keyout",
        str(key),
        "-out",
        str(csr),
    )
    run(
        "openssl",
        "x509",
        "-req",
        "-in",
        str(csr),
        "-CA",
        str(ca_certificate),
        "-CAkey",
        str(ca_key),
        "-CAcreateserial",
        "-days",
        "30",
        "-sha256",
        "-extfile",
        str(extensions),
        "-extensions",
        "server",
        "-out",
        str(certificate),
    )
    return certificate, key


def create_bad_client(
    directory: Path, agent_id: str, *, expired: bool, ca_certificate: Path, ca_key: Path
) -> tuple[Path, Path]:
    key = directory / f"{agent_id}.key"
    csr = directory / f"{agent_id}.csr"
    certificate = directory / f"{agent_id}.crt"
    extensions = directory / f"{agent_id}-extensions.cnf"
    extensions.write_text(
        "[agent]\nbasicConstraints=critical,CA:FALSE\n"
        f"subjectAltName=URI:urn:edr:agent:{agent_id}\n"
        "extendedKeyUsage=clientAuth\nkeyUsage=critical,digitalSignature\n",
        encoding="utf-8",
    )
    run(
        "openssl",
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        f"/CN={agent_id}",
        "-addext",
        f"subjectAltName=URI:urn:edr:agent:{agent_id}",
        "-addext",
        "extendedKeyUsage=clientAuth",
        "-keyout",
        str(key),
        "-out",
        str(csr),
    )
    if expired:
        ca_database = directory / f"{agent_id}-ca-db"
        ca_database.mkdir()
        (ca_database / "newcerts").mkdir()
        (ca_database / "index.txt").write_text("", encoding="utf-8")
        (ca_database / "serial").write_text("1000\n", encoding="ascii")
        ca_config = ca_database / "ca.cnf"
        ca_config.write_text(
            "[ca]\ndefault_ca=default\n[default]\n"
            f"database={ca_database / 'index.txt'}\n"
            f"new_certs_dir={ca_database / 'newcerts'}\n"
            f"certificate={ca_certificate}\nprivate_key={ca_key}\n"
            f"serial={ca_database / 'serial'}\ndefault_md=sha256\n"
            "policy=policy\n[policy]\ncommonName=supplied\n[agent]\n"
            "basicConstraints=critical,CA:FALSE\n"
            f"subjectAltName=URI:urn:edr:agent:{agent_id}\n"
            "extendedKeyUsage=clientAuth\nkeyUsage=critical,digitalSignature\n",
            encoding="utf-8",
        )
        run(
            "openssl",
            "ca",
            "-batch",
            "-config",
            str(ca_config),
            "-in",
            str(csr),
            "-startdate",
            "240101000000Z",
            "-enddate",
            "250101000000Z",
            "-extensions",
            "agent",
            "-out",
            str(certificate),
        )
    else:
        run(
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr),
            "-signkey",
            str(key),
            "-days",
            "30",
            "-sha256",
            "-extfile",
            str(extensions),
            "-extensions",
            "agent",
            "-out",
            str(certificate),
        )
    return certificate, key


def buffer_metrics(state: Path) -> dict[str, int]:
    with sqlite3.connect(state / "events.sqlite3") as connection:
        pending, failed, retries = connection.execute(
            "SELECT count(*) FILTER (WHERE status='PENDING'), count(*) FILTER (WHERE status='FAILED'), "
            "coalesce(sum(retry_count),0) FROM local_event_buffer"
        ).fetchone()
    return {"pending": pending, "failed": failed, "retryCount": retries}


def assigned_batch_ids(state: Path) -> list[str]:
    with sqlite3.connect(state / "events.sqlite3") as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT batch_id FROM local_event_buffer WHERE batch_id IS NOT NULL ORDER BY batch_id"
            )
        ]


def agent_config(
    path: Path, *, agent_id: str, state: Path, watch: Path, certificate: Path, key: Path, ca: Path
) -> Path:
    payload = {
        "agentId": agent_id,
        "collectorBaseUrl": "https://127.0.0.1:58443/api/v1",
        "certificatePath": str(certificate),
        "privateKeyPath": str(key),
        "caCertificatePath": str(ca),
        "stateDirectory": str(state),
        "watchDirectory": str(watch),
        "captureInterface": "lo0",
        "queueMaxEvents": 2000,
        "retryBaseSeconds": 1,
        "retryMaxSeconds": 4,
        "logLevel": "INFO",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def execute_agent(
    binary: Path, config: Path, watch: Path, *, trigger_detection: bool
) -> subprocess.CompletedProcess[str]:
    watch.mkdir(parents=True, exist_ok=True)

    def write_observed_file() -> None:
        time.sleep(0.5)
        (watch / f"observed-{uuid4()}.txt").write_text("metadata only", encoding="utf-8")

    writer = threading.Thread(target=write_observed_file)
    writer.start()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client_socket = socket.create_connection(listener.getsockname())
    server_socket, _ = listener.accept()
    suspicious = None
    if trigger_detection:
        suspicious = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(15)", "-EncodedCommand", "QQ=="],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    try:
        return subprocess.run(
            [str(binary), "--config", str(config), "--once", "--collect-seconds", "2"],
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )
    finally:
        writer.join()
        server_socket.close()
        client_socket.close()
        listener.close()
        if suspicious is not None:
            suspicious.terminate()
            suspicious.wait(timeout=5)


def consume(worker: object, *, maximum: int = 3000) -> int:
    consumed = 0
    idle = 0
    for _ in range(maximum):
        if worker.run_once(0.1):  # type: ignore[attr-defined]
            consumed += 1
            idle = 0
        else:
            idle += 1
            if consumed and idle >= 8:
                break
    return consumed


def request_json(
    url: str, *, method: str = "GET", body: dict | None = None, token: str | None = None
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        method=method,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-binary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    # Colima는 /Users 아래의 host 경로만 test container에 bind mount한다.
    temporary = Path(tempfile.mkdtemp(prefix="edr-agent-e2e-", dir=ROOT.parent))
    report: dict[str, object] = {"temporaryDirectory": str(temporary)}
    postgres_dsn = os.environ["TEST_POSTGRES_DSN"]
    clickhouse_password = os.environ["TEST_CLICKHOUSE_PASSWORD"]
    s3_secret = os.environ["TEST_S3_SECRET_KEY"]
    bootstrap = os.getenv("TEST_KAFKA_BOOTSTRAP", "127.0.0.1:59092")
    s3_endpoint = os.getenv("TEST_S3_ENDPOINT", "http://127.0.0.1:59000")
    postgres_up = ROOT / "migrations/postgresql/0001_initial.up.sql"
    postgres_down = ROOT / "migrations/postgresql/0001_initial.down.sql"
    refresh_sessions_up = ROOT / "migrations/postgresql/0002_refresh_sessions.up.sql"
    refresh_sessions_down = ROOT / "migrations/postgresql/0002_refresh_sessions.down.sql"
    clickhouse_up = ROOT / "migrations/clickhouse/0001_initial.up.sql"
    clickhouse_down = ROOT / "migrations/clickhouse/0001_initial.down.sql"
    clickhouse = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=58123,
        username="edr",
        password=clickhouse_password,
        database="edr",
        autogenerate_session_id=False,
    )
    with psycopg.connect(postgres_dsn) as connection:
        apply_postgres_file(connection, refresh_sessions_down)
        apply_postgres_file(connection, postgres_down)
        apply_postgres_file(connection, postgres_up)
        apply_postgres_file(connection, refresh_sessions_up)
        now = datetime.now(UTC)
        connection.execute(
            "INSERT INTO users(email,password_hash,name,role,status,created_at,updated_at) "
            "VALUES(%s,%s,%s,'ADMIN','ACTIVE',%s,%s)",
            ("e2e-admin@example.com", hash_password("e2e-admin-password"), "E2E Administrator", now, now),
        )
        connection.commit()
    apply_clickhouse_file(clickhouse, clickhouse_down)
    apply_clickhouse_file(clickhouse, clickhouse_up)
    admin = AdminClient({"bootstrap.servers": bootstrap})
    existing = [topic for topic in TOPICS if topic in admin.list_topics(timeout=10).topics]
    if existing:
        for future in admin.delete_topics(existing).values():
            future.result(10)
    ensure_topics(bootstrap)
    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id="edr-local",
        aws_secret_access_key=s3_secret,
        region_name="us-east-1",
    )
    try:
        s3.create_bucket(Bucket="edr-agent-e2e")
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "BucketAlreadyOwnedByYou":
            raise
    settings = Settings(
        jwt_secret="agent-e2e-integration-jwt-secret-32-bytes-minimum",
        postgres_dsn=postgres_dsn,
        clickhouse_dsn=f"http://edr:{clickhouse_password}@127.0.0.1:58123/edr",
        kafka_bootstrap_servers=bootstrap,
        s3_endpoint_url=s3_endpoint,
        s3_access_key_id="edr-local",
        s3_secret_access_key=s3_secret,
        s3_bucket="edr-agent-e2e",
        agent_ca_cert_path="certs/ca.crt",
        agent_ca_key_path="certs/ca.key",
        _env_file=None,
    )
    runtime = RuntimeServices(settings)
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(create_app(runtime), host="127.0.0.1", port=58877, log_level="warning")
    )
    backend_thread = threading.Thread(target=uvicorn_server.run)
    backend_thread.start()
    while not uvicorn_server.started:
        time.sleep(0.05)

    certificates = provision("agent-mac-e2e", temporary / "certs")
    server_certificate, server_key = create_server_certificate(
        temporary, temporary / "certs/ca/ca.crt", temporary / "certs/ca/ca.key"
    )
    state = temporary / "agent-state"
    watch = temporary / "watch"
    config = agent_config(
        temporary / "agent-config.json",
        agent_id="agent-mac-e2e",
        state=state,
        watch=watch,
        certificate=certificates.certificate,
        key=certificates.private_key,
        ca=certificates.ca_certificate,
    )

    offline = execute_agent(arguments.agent_binary, config, watch, trigger_detection=True)
    offline_batch_ids = assigned_batch_ids(state)
    report["offline"] = {
        "stdout": offline.stdout.strip().splitlines(),
        "buffer": buffer_metrics(state),
        "assignedBatchIds": offline_batch_ids,
    }

    nginx_name = start_nginx(
        temporary,
        certificate=server_certificate,
        private_key=server_key,
        client_ca=temporary / "certs/ca/ca.crt",
        agent_certificate=certificates.certificate,
        agent_id="agent-mac-e2e",
        fingerprint_sha256=certificates.fingerprint_sha256,
    )
    spoof_status, spoof_response = mtls_request_json(
        "https://127.0.0.1:58443/api/v1/collector/agents/register",
        body={
            "agentId": "agent-mac-e2e",
            "hostname": "agent-e2e-nginx-spoof-check",
            "osType": "MACOS",
            "osVersion": "test",
            "agentVersion": "0.1.0",
            "agentBuildId": "agent-e2e-nginx",
            "agentArch": "ARM64",
            "capabilityCodes": [],
        },
        certificate=certificates.certificate,
        private_key=certificates.private_key,
        ca_certificate=certificates.ca_certificate,
        spoof_identity_headers=True,
    )
    online = execute_agent(arguments.agent_binary, config, watch, trigger_detection=True)
    report["online"] = {"stdout": online.stdout.strip().splitlines(), "buffer": buffer_metrics(state)}
    with runtime.postgres() as connection:
        projected_identity = connection.execute(
            """
            SELECT cert_fingerprint, cert_subject, cert_san_agent_id, issued_at, expires_at
            FROM agent_auth_keys
            JOIN endpoints USING (endpoint_id)
            WHERE endpoints.agent_id = 'agent-mac-e2e' AND agent_auth_keys.revoked_at IS NULL
            """
        ).fetchone()
    nginx_test = subprocess.run(
        ["docker", "exec", nginx_name, "nginx", "-t", "-c", "/agent-e2e/nginx.conf"],
        check=True,
        capture_output=True,
        text=True,
    )
    report["nginx"] = {
        "configTest": (nginx_test.stdout + nginx_test.stderr).strip().splitlines(),
        "spoofedRegisterStatus": spoof_status,
        "spoofedRegisterAgentId": spoof_response["data"]["agentId"],
        "projectedFingerprint": projected_identity[0],
        "projectedSubject": projected_identity[1],
        "projectedSanAgentId": projected_identity[2],
        "projectedNotBefore": projected_identity[3],
        "projectedNotAfter": projected_identity[4],
        "externalHeadersOverwritten": projected_identity[0].lower() == certificates.fingerprint_sha256.lower()
        and projected_identity[1] != "CN=external-spoof"
        and projected_identity[2] == "agent-mac-e2e",
    }

    failure_sink = FailureSink(
        s3_client=runtime.s3, bucket="edr-agent-e2e", repository=FailureRepository(runtime.clickhouse)
    )
    raw_consumer = KafkaConsumer(bootstrap, group_id=f"agent-e2e-storage-{uuid4()}", topic=RAW_TOPIC)
    detection_consumer = KafkaConsumer(bootstrap, group_id=f"agent-e2e-detection-{uuid4()}", topic=VALIDATED_TOPIC)
    try:
        with runtime.postgres() as connection:
            stored = consume(
                EventStorageWorker(
                    consumer=raw_consumer,
                    producer=runtime.producer,
                    events=EventRepository(runtime.clickhouse),
                    metadata=IngestMetadataRepository(connection),
                    failure_sink=failure_sink,
                    sleep=lambda _: None,
                )
            )
        with runtime.postgres() as connection:
            detected = consume(
                DetectionWorker(
                    consumer=detection_consumer,
                    engine=DetectionEngine(runtime.rules),
                    alerts=AlertRepository(connection),
                    incidents=IncidentRepository(connection),
                    failure_sink=failure_sink,
                    sleep=lambda _: None,
                )
            )
    finally:
        raw_consumer.close()
        detection_consumer.close()

    event_count, unique_count = clickhouse.query(
        "SELECT count(), uniqExact(event_id) FROM edr_events WHERE agent_id='agent-mac-e2e'"
    ).result_rows[0]
    by_type = dict(
        clickhouse.query(
            "SELECT event_type, count() FROM edr_events WHERE agent_id='agent-mac-e2e' "
            "GROUP BY event_type ORDER BY event_type"
        ).result_rows
    )
    with runtime.postgres() as connection:
        endpoint = connection.execute(
            "SELECT endpoint_id,status,sensor_health_json FROM endpoints WHERE agent_id='agent-mac-e2e'"
        ).fetchone()
        alert_count = connection.execute("SELECT count(*) FROM alerts").fetchone()[0]
        incident_count = connection.execute("SELECT count(*) FROM incidents").fetchone()[0]
    report["workers"] = {"rawConsumed": stored, "validatedConsumed": detected}
    report["storage"] = {
        "eventCount": event_count,
        "uniqueEventCount": unique_count,
        "duplicates": event_count - unique_count,
        "byType": by_type,
        "alertCount": alert_count,
        "incidentCount": incident_count,
    }
    stored_batch_ids = [
        str(row[0])
        for row in clickhouse.query(
            "SELECT DISTINCT batch_id FROM edr_events WHERE agent_id='agent-mac-e2e' ORDER BY batch_id"
        ).result_rows
    ]
    report["batchRetransmission"] = {
        "offlineAssignedBatchIds": offline_batch_ids,
        "storedBatchIds": stored_batch_ids,
        "preserved": bool(offline_batch_ids) and all(batch_id in stored_batch_ids for batch_id in offline_batch_ids),
    }
    report["endpoint"] = {"endpointId": endpoint[0], "status": endpoint[1], "sensorHealth": endpoint[2]}

    invalid_certificate, invalid_key = create_bad_client(
        temporary,
        "agent-invalid-e2e",
        expired=False,
        ca_certificate=temporary / "certs/ca/ca.crt",
        ca_key=temporary / "certs/ca/ca.key",
    )
    invalid_state = temporary / "invalid-state"
    invalid_run = execute_agent(
        arguments.agent_binary,
        agent_config(
            temporary / "invalid.json",
            agent_id="agent-invalid-e2e",
            state=invalid_state,
            watch=temporary / "invalid-watch",
            certificate=invalid_certificate,
            key=invalid_key,
            ca=certificates.ca_certificate,
        ),
        temporary / "invalid-watch",
        trigger_detection=False,
    )
    expired_certificate, expired_key = create_bad_client(
        temporary,
        "agent-expired-e2e",
        expired=True,
        ca_certificate=temporary / "certs/ca/ca.crt",
        ca_key=temporary / "certs/ca/ca.key",
    )
    expired_state = temporary / "expired-state"
    expired_run = execute_agent(
        arguments.agent_binary,
        agent_config(
            temporary / "expired.json",
            agent_id="agent-expired-e2e",
            state=expired_state,
            watch=temporary / "expired-watch",
            certificate=expired_certificate,
            key=expired_key,
            ca=certificates.ca_certificate,
        ),
        temporary / "expired-watch",
        trigger_detection=False,
    )
    report["certificateFailures"] = {
        "invalid": {"stderr": invalid_run.stderr.strip().splitlines(), "buffer": buffer_metrics(invalid_state)},
        "expired": {"stderr": expired_run.stderr.strip().splitlines(), "buffer": buffer_metrics(expired_state)},
    }

    with runtime.postgres() as connection:
        connection.execute("UPDATE endpoints SET status='RETIRED' WHERE agent_id='agent-mac-e2e'")
        connection.commit()
    retired = execute_agent(arguments.agent_binary, config, watch, trigger_detection=False)
    report["retired"] = {"stderr": retired.stderr.strip().splitlines(), "buffer": buffer_metrics(state)}
    with runtime.postgres() as connection:
        connection.execute("UPDATE endpoints SET status='ONLINE' WHERE agent_id='agent-mac-e2e'")
        connection.commit()

    login_status, login = request_json(
        "http://127.0.0.1:58877/api/v1/auth/login",
        method="POST",
        body={"email": "e2e-admin@example.com", "password": "e2e-admin-password"},
    )
    token = login["data"]["accessToken"]
    endpoint_status, endpoint_api = request_json("http://127.0.0.1:58877/api/v1/endpoints", token=token)
    event_status, event_api = request_json("http://127.0.0.1:58877/api/v1/events", token=token)
    alert_status, alert_api = request_json("http://127.0.0.1:58877/api/v1/alerts", token=token)
    dashboard_status, dashboard_api = request_json(
        "http://127.0.0.1:58877/api/v1/dashboard/summary?timePreset=LATEST_24H&interval=1h", token=token
    )
    report["api"] = {
        "login": login_status,
        "endpoints": endpoint_status,
        "events": event_status,
        "alerts": alert_status,
        "dashboard": dashboard_status,
        "endpointTotal": endpoint_api["data"]["total"],
        "eventTotal": event_api["data"]["total"],
        "alertTotal": alert_api["data"]["total"],
        "dashboardEvents": dashboard_api["data"]["events"]["totalCount"],
    }
    pcap_files = [str(path) for path in temporary.rglob("*") if path.is_file() and "pcap" in path.name.lower()]
    pcap_files += [
        str(path) for path in ROOT.rglob("*") if path.is_file() and path.suffix.lower() in {".pcap", ".pcapng"}
    ]
    s3_keys = [item["Key"] for item in s3.list_objects_v2(Bucket="edr-agent-e2e").get("Contents", [])]
    report["pcap"] = {"files": pcap_files, "s3Keys": [key for key in s3_keys if "pcap" in key.lower()]}
    nginx_logs = subprocess.run(["docker", "logs", nginx_name], check=True, capture_output=True, text=True)
    report["nginx"]["accessAndErrorLogs"] = (nginx_logs.stdout + nginx_logs.stderr).strip().splitlines()
    arguments.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))

    subprocess.run(["docker", "stop", nginx_name], check=True, capture_output=True)
    uvicorn_server.should_exit = True
    backend_thread.join()
    clickhouse.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
