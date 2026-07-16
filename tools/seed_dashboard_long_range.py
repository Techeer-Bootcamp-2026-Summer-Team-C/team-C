from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from types import ModuleType
from uuid import NAMESPACE_URL, UUID, uuid5

import clickhouse_connect
import psycopg

from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.workers import normalize_event

ROOT = Path(__file__).parents[1]
BASE_SEED_PATH = ROOT / "tests" / "seed_frontend_qa.py"
MAX_GENERATED_EVENTS = 250_000
EVENT_TYPES = ("PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT", "DNS_QUERY", "L7_EVENT")
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
ALERT_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED")
FAILURE_STATUSES = ("FAILED", "REPROCESSED", "REPROCESS_FAILED")
ARCHIVE_STATUSES = ("ARCHIVED", "RESTORE_REQUESTED", "RESTORE_FAILED", "EXPIRED")


@dataclass(frozen=True, slots=True)
class SeedConfig:
    days: int = 7
    endpoint_count: int = 20
    events_per_endpoint_day: int = 100
    seed: int = 20_260_715

    @property
    def event_count(self) -> int:
        return self.days * self.endpoint_count * self.events_per_endpoint_day

    @property
    def alerts_per_endpoint(self) -> int:
        return max(4, self.days * 2)

    @property
    def alert_count(self) -> int:
        return self.endpoint_count * self.alerts_per_endpoint

    @property
    def incident_count(self) -> int:
        return self.endpoint_count * 2

    @property
    def failure_count(self) -> int:
        return max(12, self.endpoint_count * self.days // 4)

    @property
    def hot_bucket_count(self) -> int:
        # A rolling N-day range overlaps N+1 UTC calendar buckets unless it starts at midnight.
        return self.endpoint_count * (self.days + 1)

    def validate(self) -> None:
        if not 7 <= self.days <= 31:
            raise ValueError("days must be between 7 and 31")
        if not 3 <= self.endpoint_count <= 100:
            raise ValueError("endpoints must be between 3 and 100")
        if not 10 <= self.events_per_endpoint_day <= 1_000:
            raise ValueError("events-per-endpoint-day must be between 10 and 1000")
        if self.event_count > MAX_GENERATED_EVENTS:
            raise ValueError(f"requested event count exceeds the safety limit of {MAX_GENERATED_EVENTS:,}")


@dataclass(frozen=True, slots=True)
class EndpointSeed:
    endpoint_id: int
    agent_id: str
    hostname: str
    os_type: str
    os_version: str | None
    ip_address: str | None
    agent_version: str | None
    agent_build_id: str | None
    agent_arch: str | None
    status: str
    registered_at: datetime
    event_window_start: datetime
    event_window_end: datetime


@dataclass(frozen=True, slots=True)
class EventRef:
    event_id: UUID
    batch_id: UUID
    endpoint_id: int
    event_type: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class AlertRef:
    alert_id: int
    endpoint_id: int
    severity: str
    detected_at: datetime


RULES = {
    "PROCESS_EXECUTION": (
        "PROC_POWERSHELL_ENCODED",
        "PowerShell Encoded Command",
        "TA0002",
        "Execution",
        "T1059.001",
        "PowerShell",
    ),
    "NETWORK_CONNECTION": (
        "NET_SUSPICIOUS_EGRESS",
        "Suspicious Egress Destination",
        "TA0011",
        "Command and Control",
        "T1071.001",
        "Web Protocols",
    ),
    "FILE_EVENT": (
        "FILE_SUSPICIOUS_DROP",
        "Suspicious File Drop",
        "TA0003",
        "Persistence",
        "T1547.001",
        "Registry Run Keys / Startup Folder",
    ),
    "DNS_QUERY": (
        "DNS_RARE_DOMAIN",
        "Rare Domain Query",
        "TA0011",
        "Command and Control",
        "T1071.004",
        "DNS",
    ),
    "L7_EVENT": (
        "L7_UPLOAD_ANOMALY",
        "Unusual HTTPS Upload",
        "TA0010",
        "Exfiltration",
        "T1048.003",
        "Exfiltration Over Unencrypted Non-C2 Protocol",
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset the local QA databases and seed a deterministic multi-endpoint dashboard history."
    )
    parser.add_argument("--days", type=int, default=7, help="Rolling history length, 7..31 (default: 7).")
    parser.add_argument("--endpoints", type=int, default=20, help="Total Endpoint count, 3..100 (default: 20).")
    parser.add_argument(
        "--events-per-endpoint-day",
        type=int,
        default=100,
        help="Event density per Endpoint per day, 10..1000 (default: 100).",
    )
    parser.add_argument("--seed", type=int, default=20_260_715, help="Deterministic data-shape seed.")
    parser.add_argument("--dry-run", action="store_true", help="Print estimated row counts without changing data.")
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Required for execution because PostgreSQL and ClickHouse QA data are reset.",
    )
    return parser


def parse_config(args: argparse.Namespace) -> SeedConfig:
    config = SeedConfig(
        days=args.days,
        endpoint_count=args.endpoints,
        events_per_endpoint_day=args.events_per_endpoint_day,
        seed=args.seed,
    )
    config.validate()
    return config


def build_endpoint_seeds(config: SeedConfig, *, now: datetime) -> list[EndpointSeed]:
    start = now - timedelta(days=config.days) + timedelta(minutes=5)
    seeds: list[EndpointSeed] = []
    for endpoint_id in range(1, config.endpoint_count + 1):
        if endpoint_id == 1:
            hostname, agent_id, os_type = "SOC-WIN-01", "agent-soc-001", "WINDOWS"
        elif endpoint_id == 2:
            hostname, agent_id, os_type = "FINANCE-MAC-02", "agent-finance-mac-002", "MACOS"
        elif endpoint_id == 3:
            hostname, agent_id, os_type = (
                "RETIRED-LAB-ENDPOINT-WITH-A-LONG-HOSTNAME-003",
                "agent-retired-lab-003",
                "WINDOWS",
            )
        else:
            os_type = "MACOS" if endpoint_id % 3 == 0 else "WINDOWS"
            prefix = "FIN-MAC" if os_type == "MACOS" else "ENG-WIN"
            hostname = f"{prefix}-{endpoint_id:03d}"
            agent_id = f"agent-{'mac' if os_type == 'MACOS' else 'win'}-{endpoint_id:03d}"

        if endpoint_id == 3 or endpoint_id % 10 == 0:
            status = "RETIRED"
            window_end = now - timedelta(days=2)
        elif endpoint_id == 2 or endpoint_id % 4 == 0:
            status = "OFFLINE"
            window_end = now - timedelta(hours=12)
        else:
            status = "ONLINE"
            window_end = now - timedelta(minutes=1)

        os_version = "macOS 15.5" if os_type == "MACOS" else "Windows 11 24H2"
        agent_arch = "ARM64" if os_type == "MACOS" else "X64"
        third_octet = (endpoint_id - 1) // 250
        fourth_octet = (endpoint_id - 1) % 250 + 1
        seeds.append(
            EndpointSeed(
                endpoint_id=endpoint_id,
                agent_id=agent_id,
                hostname=hostname,
                os_type=os_type,
                os_version=os_version,
                ip_address=f"10.24.{third_octet}.{fourth_octet}",
                agent_version=f"2.7.{endpoint_id % 4}",
                agent_build_id=f"{os_type.lower()}-{agent_arch.lower()}-qa-{endpoint_id:03d}",
                agent_arch=agent_arch,
                status=status,
                registered_at=now - timedelta(days=config.days + 30 + endpoint_id),
                event_window_start=start,
                event_window_end=window_end,
            )
        )
    return seeds


def _sensor_health(endpoint: EndpointSeed) -> list[dict[str, object]]:
    if endpoint.endpoint_id % 11 == 0:
        network_status = "UNAVAILABLE"
    elif endpoint.endpoint_id % 6 == 0:
        network_status = "DEGRADED"
    else:
        network_status = "HEALTHY"
    return [
        {
            "sensor": "PROCESS",
            "status": "HEALTHY",
            "provider": "EndpointSecurity" if endpoint.os_type == "MACOS" else "ETW",
            "packetDropCount": 0,
            "parseErrorCount": endpoint.endpoint_id % 3,
        },
        {
            "sensor": "NETWORK",
            "status": network_status,
            "provider": "NetworkExtension" if endpoint.os_type == "MACOS" else "WFP",
            "packetDropCount": endpoint.endpoint_id * 3 if network_status != "HEALTHY" else 0,
            "parseErrorCount": endpoint.endpoint_id % 5 if network_status != "HEALTHY" else 0,
        },
    ]


def _insert_endpoint_inventory(connection: psycopg.Connection, endpoints: list[EndpointSeed], *, now: datetime) -> None:
    new_rows = []
    for endpoint in endpoints[3:]:
        capabilities = (
            list(EVENT_TYPES) if endpoint.os_type == "WINDOWS" else ["PROCESS_EXECUTION", "NETWORK_CONNECTION"]
        )
        new_rows.append(
            (
                endpoint.endpoint_id,
                endpoint.agent_id,
                endpoint.hostname,
                endpoint.os_type,
                endpoint.os_version,
                endpoint.ip_address,
                endpoint.agent_version,
                endpoint.agent_build_id,
                endpoint.agent_arch,
                json.dumps(capabilities),
                json.dumps(_sensor_health(endpoint)),
                endpoint.registered_at,
                endpoint.status,
                endpoint.event_window_end,
                now,
                now,
            )
        )
    if new_rows:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO endpoints (
                    endpoint_id, agent_id, hostname, os_type, os_version, ip_address, agent_version,
                    agent_build_id, agent_arch, capability_codes_json, sensor_health_json,
                    registered_at, status, last_seen_at, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s
                )
                """,
                new_rows,
            )

    for endpoint in endpoints[:3]:
        connection.execute(
            """
            UPDATE endpoints
            SET status = %s, last_seen_at = %s, sensor_health_json = %s::jsonb, updated_at = %s
            WHERE endpoint_id = %s
            """,
            (
                endpoint.status,
                endpoint.event_window_end,
                json.dumps(_sensor_health(endpoint)),
                now,
                endpoint.endpoint_id,
            ),
        )

    connection.execute(
        "SELECT setval(pg_get_serial_sequence('endpoints', 'endpoint_id'), "
        "(SELECT MAX(endpoint_id) FROM endpoints), TRUE)"
    )
    certificate_rows = []
    for endpoint in endpoints[1:]:
        issued_at = now - timedelta(days=180 + endpoint.endpoint_id)
        revoked_at = now - timedelta(days=2) if endpoint.status == "RETIRED" else None
        expires_at = (
            now - timedelta(days=1)
            if endpoint.status == "OFFLINE" and endpoint.endpoint_id % 8 == 0
            else now + timedelta(days=180)
        )
        fingerprint = hashlib.sha256(f"long-range-cert:{endpoint.endpoint_id}".encode()).hexdigest()
        certificate_rows.append(
            (
                endpoint.endpoint_id,
                fingerprint,
                f"CN={endpoint.agent_id},O=EDR Long Range QA",
                endpoint.agent_id,
                issued_at,
                expires_at,
                revoked_at,
                now,
                now,
            )
        )
    if certificate_rows:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO agent_auth_keys (
                    endpoint_id, cert_fingerprint, cert_subject, cert_san_agent_id,
                    issued_at, expires_at, revoked_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                certificate_rows,
            )
    connection.commit()


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _event_payload(endpoint: EndpointSeed, event_type: str, index: int) -> dict[str, object]:
    pid = 100_000 + endpoint.endpoint_id * 1_000 + index
    domains = (
        "updates.example.net",
        "api.corp.example",
        "cdn.example.org",
        "rare-beacon.example.net",
        "storage.example.com",
    )
    domain = domains[(endpoint.endpoint_id + index) % len(domains)]
    if event_type == "PROCESS_EXECUTION":
        process_names = ("powershell.exe", "chrome.exe", "python.exe", "launchctl", "cmd.exe")
        process_name = process_names[(endpoint.endpoint_id + index) % len(process_names)]
        previous_process_pid = pid - 5 if index >= 5 else 4
        return {
            "processName": process_name,
            "processPath": f"/qa/bin/{process_name}" if endpoint.os_type == "MACOS" else f"C:\\QA\\bin\\{process_name}",
            "pid": pid,
            "ppid": previous_process_pid,
            "commandLine": (
                "powershell -EncodedCommand SQBFAFgA" if index % 17 == 0 else f"{process_name} --qa-run {index}"
            ),
            "userName": f"QA\\user{endpoint.endpoint_id:02d}",
        }
    if event_type == "NETWORK_CONNECTION":
        return {
            "protocol": "TCP" if index % 4 else "UDP",
            "remoteIp": f"203.0.113.{(endpoint.endpoint_id * 13 + index) % 250 + 1}",
            "remotePort": (443, 53, 80, 8443)[index % 4],
            "remoteDomain": domain,
            "processName": "powershell.exe" if index % 9 == 0 else "chrome.exe",
            "pid": pid,
        }
    if event_type == "FILE_EVENT":
        file_path = (
            f"/Users/qa/Library/Caches/artifact-{endpoint.endpoint_id:03d}-{index:05d}.bin"
            if endpoint.os_type == "MACOS"
            else f"C:\\ProgramData\\QA\\artifact-{endpoint.endpoint_id:03d}-{index:05d}.bin"
        )
        return {
            "filePath": file_path,
            "action": ("CREATE", "MODIFY", "DELETE")[index % 3],
            "sha256": hashlib.sha256(f"artifact:{endpoint.endpoint_id}:{index}".encode()).hexdigest(),
            "processName": "python.exe",
            "pid": pid,
        }
    if event_type == "DNS_QUERY":
        return {
            "query": domain,
            "recordType": ("A", "AAAA", "TXT")[index % 3],
            "responseCode": "NXDOMAIN" if index % 11 == 0 else "NOERROR",
            "answers": [] if index % 11 == 0 else [f"198.51.100.{index % 250 + 1}"],
            "processName": "chrome.exe",
            "pid": pid,
        }
    return {
        "l7Protocol": ("HTTPS", "HTTP", "TLS")[index % 3],
        "httpMethod": ("GET", "POST", "PUT")[index % 3],
        "httpHost": domain,
        "url": f"https://{domain}/qa/endpoint/{endpoint.endpoint_id}/event/{index}",
        "httpStatusCode": (200, 202, 403, 500)[index % 4],
        "httpUserAgent": f"EDR-QA-Agent/{endpoint.endpoint_id}",
        "tlsSni": domain,
        "tlsVersion": "TLS1.3" if index % 5 else "TLS1.2",
        "tlsCertificateSubject": f"CN={domain}",
        "tlsCertificateIssuer": "CN=EDR QA Test CA",
        "tlsCertificateSha256": hashlib.sha256(f"tls:{domain}".encode()).hexdigest(),
    }


def _raw_event(endpoint: EndpointSeed, *, index: int, event_type: str, occurred_at: datetime, seed: int) -> dict:
    event_id = uuid5(NAMESPACE_URL, f"team-c-long-range:event:{seed}:{endpoint.endpoint_id}:{index}")
    batch_id = uuid5(NAMESPACE_URL, f"team-c-long-range:batch:{seed}:{endpoint.endpoint_id}:{index // 25}")
    return {
        "schemaVersion": 1,
        "batchId": str(batch_id),
        "endpointId": endpoint.endpoint_id,
        "agentId": endpoint.agent_id,
        "hostname": endpoint.hostname,
        "osType": endpoint.os_type,
        "ipAddress": endpoint.ip_address,
        "event": {
            "eventId": str(event_id),
            "eventType": event_type,
            "occurredAt": _rfc3339(occurred_at),
            "payload": _event_payload(endpoint, event_type, index),
        },
    }


def _generate_events(
    client,
    endpoints: list[EndpointSeed],
    config: SeedConfig,
    *,
    now: datetime,
) -> tuple[dict[int, list[EventRef]], Counter[tuple[int, object]]]:
    rng = random.Random(config.seed)
    repository = EventRepository(client)
    references: dict[int, list[EventRef]] = {}
    counts_by_day: Counter[tuple[int, object]] = Counter()
    events_per_endpoint = config.days * config.events_per_endpoint_day
    for endpoint in endpoints:
        span = endpoint.event_window_end - endpoint.event_window_start
        rows: list[dict] = []
        endpoint_refs: list[EventRef] = []
        for index in range(events_per_endpoint):
            ratio = (index + rng.random()) / events_per_endpoint
            occurred_at = endpoint.event_window_start + span * ratio
            ingested_at = min(occurred_at + timedelta(seconds=rng.randint(2, 120)), now - timedelta(seconds=1))
            event_type = EVENT_TYPES[(endpoint.endpoint_id + index) % len(EVENT_TYPES)]
            row = normalize_event(
                _raw_event(
                    endpoint,
                    index=index,
                    event_type=event_type,
                    occurred_at=occurred_at,
                    seed=config.seed,
                ),
                ingested_at=ingested_at,
            )
            rows.append(row)
            endpoint_refs.append(
                EventRef(
                    event_id=row["event_id"],
                    batch_id=row["batch_id"],
                    endpoint_id=endpoint.endpoint_id,
                    event_type=event_type,
                    occurred_at=occurred_at,
                )
            )
            counts_by_day[(endpoint.endpoint_id, occurred_at.date())] += 1
            if len(rows) == 1_000:
                repository.insert(rows)
                rows.clear()
        repository.insert(rows)
        references[endpoint.endpoint_id] = endpoint_refs
    return references, counts_by_day


def _insert_alerts_and_incidents(
    connection: psycopg.Connection,
    endpoints: list[EndpointSeed],
    event_refs: dict[int, list[EventRef]],
    config: SeedConfig,
    *,
    now: datetime,
) -> tuple[int, int]:
    next_alert_id = int(connection.execute("SELECT COALESCE(MAX(alert_id), 0) + 1 FROM alerts").fetchone()[0])
    alert_rows = []
    alert_refs: dict[int, list[AlertRef]] = {}
    for endpoint in endpoints:
        candidates = event_refs[endpoint.endpoint_id]
        selected: list[AlertRef] = []
        for alert_index in range(config.alerts_per_endpoint):
            candidate_index = min(
                int((alert_index + 0.5) * len(candidates) / config.alerts_per_endpoint),
                len(candidates) - 1,
            )
            event = candidates[candidate_index]
            rule = RULES[event.event_type]
            severity = SEVERITIES[(endpoint.endpoint_id + alert_index) % len(SEVERITIES)]
            status = ALERT_STATUSES[(endpoint.endpoint_id + alert_index) % len(ALERT_STATUSES)]
            risk_score = {"LOW": 24, "MEDIUM": 49, "HIGH": 76, "CRITICAL": 94}[severity]
            detected_at = min(event.occurred_at + timedelta(minutes=5), now - timedelta(seconds=5))
            alert_id = next_alert_id
            next_alert_id += 1
            alert_rows.append(
                (
                    alert_id,
                    endpoint.endpoint_id,
                    event.event_id,
                    event.occurred_at,
                    event.batch_id,
                    endpoint.agent_id,
                    rule[0],
                    rule[1],
                    1,
                    rule[2],
                    rule[3],
                    rule[4],
                    rule[5],
                    f"{rule[1]} on {endpoint.hostname}",
                    f"Deterministic long-range QA alert for {endpoint.agent_id}.",
                    severity,
                    risk_score,
                    status,
                    detected_at,
                    detected_at,
                    detected_at,
                )
            )
            selected.append(AlertRef(alert_id, endpoint.endpoint_id, severity, detected_at))
        alert_refs[endpoint.endpoint_id] = selected

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO alerts (
                alert_id, endpoint_id, event_id, event_occurred_at, batch_id, agent_id,
                rule_code, rule_name, rule_version, mitre_tactic_code, mitre_tactic_name,
                mitre_technique_code, mitre_technique_name, title, summary, severity,
                risk_score, status, detected_at, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            alert_rows,
        )
    connection.execute(
        "SELECT setval(pg_get_serial_sequence('alerts', 'alert_id'), (SELECT MAX(alert_id) FROM alerts), TRUE)"
    )

    next_incident_id = int(connection.execute("SELECT COALESCE(MAX(incident_id), 0) + 1 FROM incidents").fetchone()[0])
    next_link_id = int(
        connection.execute("SELECT COALESCE(MAX(incident_alert_id), 0) + 1 FROM incident_alerts").fetchone()[0]
    )
    incident_rows = []
    link_rows = []
    severity_rank = {value: index for index, value in enumerate(SEVERITIES)}
    for endpoint in endpoints:
        candidates = alert_refs[endpoint.endpoint_id]
        midpoint = len(candidates) // 2
        pairs = ((candidates[0], candidates[1]), (candidates[midpoint], candidates[midpoint + 1]))
        for incident_index, pair in enumerate(pairs):
            first_detected_at = min(item.detected_at for item in pair)
            last_detected_at = max(item.detected_at for item in pair)
            window_start_at = first_detected_at - timedelta(minutes=5)
            status = "OPEN" if (endpoint.endpoint_id + incident_index) % 2 == 0 else "CLOSED"
            if status == "OPEN":
                window_end_at = max(last_detected_at + timedelta(minutes=30), now + timedelta(hours=12))
                closed_at = None
            else:
                window_end_at = min(last_detected_at + timedelta(minutes=30), now - timedelta(seconds=1))
                if window_end_at <= window_start_at:
                    window_end_at = window_start_at + timedelta(minutes=1)
                closed_at = window_end_at
            severity = max((item.severity for item in pair), key=severity_rank.__getitem__)
            incident_id = next_incident_id
            next_incident_id += 1
            incident_rows.append(
                (
                    incident_id,
                    endpoint.endpoint_id,
                    f"qa-{config.seed}-endpoint-{endpoint.endpoint_id}-campaign-{incident_index + 1}",
                    window_start_at,
                    window_end_at,
                    f"Correlated {severity.lower()} activity on {endpoint.hostname}",
                    "Long-range QA Incident linking two representative Alerts.",
                    severity,
                    status,
                    first_detected_at,
                    last_detected_at,
                    closed_at,
                    last_detected_at,
                    closed_at or last_detected_at,
                )
            )
            for alert in pair:
                link_rows.append(
                    (
                        next_link_id,
                        incident_id,
                        alert.alert_id,
                        last_detected_at,
                        last_detected_at,
                        last_detected_at,
                    )
                )
                next_link_id += 1

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO incidents (
                incident_id, endpoint_id, correlation_key, window_start_at, window_end_at,
                title, description, severity, status, first_detected_at, last_detected_at,
                closed_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            incident_rows,
        )
        cursor.executemany(
            """
            INSERT INTO incident_alerts (
                incident_alert_id, incident_id, alert_id, linked_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            link_rows,
        )
    connection.execute(
        "SELECT setval(pg_get_serial_sequence('incidents', 'incident_id'), "
        "(SELECT MAX(incident_id) FROM incidents), TRUE)"
    )
    connection.execute(
        "SELECT setval(pg_get_serial_sequence('incident_alerts', 'incident_alert_id'), "
        "(SELECT MAX(incident_alert_id) FROM incident_alerts), TRUE)"
    )
    connection.commit()
    return len(alert_rows), len(incident_rows)


def _insert_storage_metadata(
    connection: psycopg.Connection,
    endpoints: list[EndpointSeed],
    counts_by_day: Counter[tuple[int, object]],
    config: SeedConfig,
    *,
    now: datetime,
) -> tuple[int, int, datetime, datetime]:
    hot_rows = []
    for endpoint in endpoints:
        for day_offset in range(config.days + 1):
            bucket_date = (now - timedelta(days=day_offset)).date()
            bucket_start = datetime.combine(bucket_date, time.min, tzinfo=UTC)
            bucket_end = bucket_start + timedelta(days=1)
            hot_rows.append(
                (
                    endpoint.endpoint_id,
                    bucket_start,
                    bucket_end,
                    f"clickhouse://edr_events/date={bucket_date.isoformat()}/endpoint_id={endpoint.endpoint_id}",
                    counts_by_day[(endpoint.endpoint_id, bucket_date)],
                    now,
                    now,
                )
            )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO ingest_metadata (
                endpoint_id, bucket_start_at, bucket_end_at, storage_backend, storage_class,
                storage_status, storage_path, event_count, created_at, updated_at
            ) VALUES (%s, %s, %s, 'CLICKHOUSE', 'HOT', 'HOT', %s, %s, %s, %s)
            ON CONFLICT (endpoint_id, bucket_start_at, storage_backend, storage_class) DO UPDATE SET
                bucket_end_at = EXCLUDED.bucket_end_at,
                storage_status = 'HOT',
                storage_path = EXCLUDED.storage_path,
                event_count = EXCLUDED.event_count,
                updated_at = EXCLUDED.updated_at,
                is_delete = FALSE
            """,
            hot_rows,
        )

    archive_rows = []
    archive_start_date = (now - timedelta(days=config.days + len(ARCHIVE_STATUSES) + 2)).date()
    archive_from = datetime.combine(archive_start_date, time.min, tzinfo=UTC)
    archive_to = datetime.combine((now - timedelta(days=config.days + 1)).date(), time.min, tzinfo=UTC)
    for index, status in enumerate(ARCHIVE_STATUSES):
        endpoint = endpoints[index % len(endpoints)]
        bucket_start = archive_from + timedelta(days=index)
        bucket_end = bucket_start + timedelta(days=1)
        restore_requested_at = bucket_start + timedelta(days=2) if status != "ARCHIVED" else None
        restored_at = bucket_start + timedelta(days=3) if status == "EXPIRED" else None
        restore_expires_at = bucket_start + timedelta(days=10) if status == "EXPIRED" else None
        last_error = "QA restore provider timeout" if status == "RESTORE_FAILED" else None
        archive_rows.append(
            (
                endpoint.endpoint_id,
                bucket_start,
                bucket_end,
                status,
                f"archives/long-range/{status.lower()}/endpoint-{endpoint.endpoint_id}-{bucket_start.date()}.parquet",
                50 + index * 25,
                4_096 + index * 2_048,
                hashlib.sha256(f"archive:{config.seed}:{status}".encode()).hexdigest(),
                bucket_start + timedelta(days=1),
                bucket_start + timedelta(days=1, hours=1),
                restore_requested_at,
                restored_at,
                restore_expires_at,
                last_error,
                now,
                now,
            )
        )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO ingest_metadata (
                endpoint_id, bucket_start_at, bucket_end_at, storage_backend, storage_class,
                storage_status, storage_path, event_count, size_bytes, checksum_sha256,
                archived_at, archive_verified_at, restore_requested_at, restored_at,
                restore_expires_at, last_error, created_at, updated_at
            ) VALUES (
                %s, %s, %s, 'S3', 'GLACIER_FLEXIBLE_RETRIEVAL', %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            archive_rows,
        )
    connection.commit()
    return len(hot_rows), len(archive_rows), archive_from, archive_to


def _insert_failures(client, event_refs: dict[int, list[EventRef]], config: SeedConfig, *, now: datetime) -> int:
    flattened = [event for endpoint_events in event_refs.values() for event in endpoint_events]
    rows = []
    stages = ("EVENT_STORAGE", "DETECTION", "SCHEMA_VALIDATION", "ARCHIVE_WRITE")
    codes = ("S3_WRITE_FAILED", "RULE_EVALUATION_FAILED", "INVALID_EVENT_SCHEMA", "ARCHIVE_TIMEOUT")
    for index in range(config.failure_count):
        event = flattened[min(int((index + 0.5) * len(flattened) / config.failure_count), len(flattened) - 1)]
        status = FAILURE_STATUSES[index % len(FAILURE_STATUSES)]
        failed_at = min(event.occurred_at + timedelta(minutes=2), now - timedelta(seconds=10))
        replayed_at = min(failed_at + timedelta(minutes=30), now - timedelta(seconds=5)) if status != "FAILED" else None
        rows.append(
            {
                "failure_id": uuid5(NAMESPACE_URL, f"team-c-long-range:failure:{config.seed}:{index}"),
                "event_id": event.event_id,
                "endpoint_id": event.endpoint_id,
                "source_topic": "telemetry.raw" if index % 2 == 0 else "telemetry.validated",
                "source_partition": index % 4,
                "source_offset": 10_000 + index,
                "consumer_name": "event-storage-worker" if index % 2 == 0 else "detection-worker",
                "failure_stage": stages[index % len(stages)],
                "failure_code": codes[index % len(codes)],
                "error_message": f"Long-range QA failure case {index + 1}",
                "retryable": 0 if index % 5 == 0 else 1,
                "retry_count": index % 4,
                "payload_object_key": f"failures/long-range/{config.seed}/{index:05d}.json.gz",
                "payload_sha256": hashlib.sha256(f"failure:{config.seed}:{index}".encode()).hexdigest(),
                "payload_size_bytes": 256 + index * 17,
                "status": status,
                "failed_at": failed_at,
                "replay_count": 0 if status == "FAILED" else 1,
                "last_replayed_at": replayed_at,
                "reprocess_outcome": (
                    None if status == "FAILED" else ("SUCCESS" if status == "REPROCESSED" else "FAILED")
                ),
                "resolved_at": replayed_at if status == "REPROCESSED" else None,
                "retention_expires_at": failed_at + timedelta(days=97),
                "created_at": failed_at,
                "updated_at": replayed_at or failed_at,
            }
        )
    FailureRepository(client).insert(rows)
    return len(rows)


def _load_base_seed() -> ModuleType:
    spec = importlib.util.spec_from_file_location("team_c_seed_frontend_qa", BASE_SEED_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load base QA seed: {BASE_SEED_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _print_estimate(config: SeedConfig) -> None:
    print("Long-range dashboard seed estimate")
    print(f"  history:          {config.days} days")
    print(f"  Endpoints:        {config.endpoint_count}")
    print(f"  Events:           {config.event_count:,}")
    print(f"  Alerts:           {config.alert_count:,}")
    print(f"  Incidents:        {config.incident_count:,}")
    print(f"  Event failures:   {config.failure_count:,}")
    print(f"  HOT buckets:      {config.hot_bucket_count:,}")
    print(f"  Archive cases:    {len(ARCHIVE_STATUSES)}")


def seed(config: SeedConfig) -> None:
    base_seed = _load_base_seed()
    base_seed.main()
    now = datetime.now(UTC).replace(microsecond=0)
    endpoints = build_endpoint_seeds(config, now=now)

    with psycopg.connect(base_seed.POSTGRES_DSN) as connection:
        _insert_endpoint_inventory(connection, endpoints, now=now)

    clickhouse = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=58123,
        username="edr",
        password=base_seed.CLICKHOUSE_PASSWORD,
        database="edr",
    )
    try:
        event_refs, counts_by_day = _generate_events(clickhouse, endpoints, config, now=now)
        failure_count = _insert_failures(clickhouse, event_refs, config, now=now)
    finally:
        clickhouse.close()

    with psycopg.connect(base_seed.POSTGRES_DSN) as connection:
        alert_count, incident_count = _insert_alerts_and_incidents(
            connection,
            endpoints,
            event_refs,
            config,
            now=now,
        )
        hot_count, archive_count, archive_from, archive_to = _insert_storage_metadata(
            connection,
            endpoints,
            counts_by_day,
            config,
            now=now,
        )

    print("\nLong-range dashboard fixture seeded")
    print(f"UTC range: {now - timedelta(days=config.days)} -> {now}")
    print(f"Endpoints: {len(endpoints)}")
    print(f"Events added: {config.event_count:,}")
    print(f"Alerts added: {alert_count:,}")
    print(f"Incidents added: {incident_count:,}")
    print(f"Event failures added: {failure_count:,}")
    print(f"HOT buckets added/updated: {hot_count:,}")
    print(f"Archive state cases added: {archive_count}")
    print(f"Archive case range: from={_rfc3339(archive_from)} to={_rfc3339(archive_to)}")
    print("ADMIN  frontend-admin / frontend-admin-password")
    print("VIEWER frontend-viewer / frontend-viewer-password")
    print("Dashboard: http://127.0.0.1:8080 (select Latest 7 days)")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = parse_config(args)
    except ValueError as error:
        parser.error(str(error))
    _print_estimate(config)
    if args.dry_run:
        return 0
    if not args.confirm_reset:
        parser.error("--confirm-reset is required because this command resets the local QA databases")
    seed(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
