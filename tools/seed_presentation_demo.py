from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, UUID, uuid5

import clickhouse_connect
import httpx
import psycopg
from clickhouse_connect.driver.exceptions import ClickHouseError
from psycopg.types.json import Jsonb

from backend.auth import hash_password
from backend.contracts.enums import OsType
from backend.detection import DetectionEngine
from backend.rule_loader import RuleLoader
from backend.storage.clickhouse import EventRepository
from backend.storage.migrations import (
    ClickHouseCommandClient,
    apply_clickhouse_file,
    apply_postgres_migrations,
    record_applied_postgres_migrations,
    split_sql_statements,
)
from backend.storage.models import EndpointInsert, IncidentInsert
from backend.storage.postgres import AlertRepository, EndpointRepository, IncidentRepository, UserRepository
from backend.workers import normalize_event
from tools.seed_safety import (
    PRODUCTION_DEMO_RESET_CONFIRMATION,
    PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
    assert_production_demo_reset_authorized,
    assert_safe_reset_targets,
    database_name,
    parse_allowed_qa_hosts,
    production_demo_target_fingerprint,
    require_reset_confirmation,
)

ROOT = Path(__file__).parents[1]
ENV_FILE = ROOT / ".env"
DEFAULT_MANIFESTS = {
    "presentation": ROOT / "runtime" / "demo" / "presentation-manifest.json",
    "dns-correctness": ROOT / "runtime" / "demo" / "dns-correctness-manifest.json",
}
PROFILES = ("presentation", "dns-correctness")
PRESENTATION_DAYS = 14
PRESENTATION_DAILY_EVENTS = {
    "GEONHA-MACMINI": 100,
    "GEONHA-WIN": 75,
    "SOYEON-WIN": 85,
    "HYERYEONG-WIN": 65,
    "JUHO-WIN": 75,
}


@dataclass(frozen=True, slots=True)
class SeedTarget:
    environment: str
    postgres_dsn: str
    clickhouse_dsn: str
    dashboard_base_url: str
    collector_base_url: str
    allowed_qa_hosts: frozenset[str] = frozenset()
    production_demo_reset_mode: str = ""
    demo_reset_target_id: str = ""
    kafka_bootstrap_servers: str = ""
    kafka_raw_topic: str = ""
    kafka_validated_topic: str = ""
    event_storage_consumer_group: str = ""
    detection_consumer_group: str = ""
    s3_bucket: str = ""


@dataclass(frozen=True, slots=True)
class EndpointPlan:
    hostname: str
    agent_id: str
    os_type: str
    os_version: str
    ip_address: str
    status: str
    event_count: int
    agent_arch: str
    owner_name: str = ""
    major: str = ""
    activity_profile: str = "generic"
    sensor_status: str = "HEALTHY"


@dataclass(frozen=True, slots=True)
class AgentFixtureMetadata:
    version: str
    build_id: str
    capability_codes: tuple[str, ...]
    sensor_health: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class EventPlan:
    hostname: str
    event_id: UUID
    batch_id: UUID
    event_type: str
    occurred_at: datetime
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProfilePlan:
    profile: str
    seed: int
    anchor: datetime
    endpoints: tuple[EndpointPlan, ...]
    events: tuple[EventPlan, ...]

    @property
    def counts(self) -> dict[str, int]:
        alert_count = 3 if self.profile == "presentation" else 0
        incident_count = 1 if self.profile == "presentation" else 0
        return {
            "endpoints": len(self.endpoints),
            "events": len(self.events),
            "alerts": alert_count,
            "incidents": incident_count,
        }


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_anchor(value: str, *, now: datetime | None = None) -> datetime:
    if value.lower() == "now":
        return (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("anchor must be 'now' or an RFC 3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("anchor must include an RFC 3339 UTC offset")
    return parsed.astimezone(UTC).replace(microsecond=0)


def agent_fixture_metadata(endpoint: EndpointPlan) -> AgentFixtureMetadata:
    """Mirror the version, capabilities, and providers reported by the shipped agents."""
    packet_status = endpoint.sensor_status
    if packet_status not in {"HEALTHY", "DEGRADED", "UNAVAILABLE"}:
        raise ValueError(f"unsupported fixture sensor status: {packet_status}")

    common_health: list[dict[str, object]] = [
        {"sensor": "PROCESS", "status": "HEALTHY"},
        {"sensor": "NETWORK", "status": "HEALTHY"},
        {"sensor": "FILE", "status": "HEALTHY"},
    ]
    packet_errors = 3 if packet_status == "DEGRADED" else 0
    if endpoint.os_type == "WINDOWS":
        capabilities = ["PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT", "DNS_QUERY"]
        common_health.append({"sensor": "DNS", "status": "HEALTHY", "provider": "DNS_CLIENT_ETW"})
        packet_provider = "NPCAP"
        build_id = "win-x64-20260712.1"
    elif endpoint.os_type == "MACOS":
        capabilities = ["PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT"]
        packet_provider = "TCPDUMP"
        build_id = "macos-arm64-20260712.1"
    else:
        raise ValueError(f"unsupported fixture OS type: {endpoint.os_type}")

    common_health.extend(
        [
            {
                "sensor": "PACKET_METADATA",
                "status": packet_status,
                "provider": packet_provider,
                "packetDropCount": 0,
            },
            {
                "sensor": "L7",
                "status": packet_status,
                "parseErrorCount": packet_errors,
            },
        ]
    )
    if packet_status == "HEALTHY":
        capabilities.extend(["DNS_QUERY", "L7_EVENT", "PACKET_METADATA_V1"])

    return AgentFixtureMetadata(
        version="0.1.0",
        build_id=build_id,
        capability_codes=tuple(dict.fromkeys(capabilities)),
        sensor_health=tuple(common_health),
    )


def load_environment_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    values.update({key: value for key, value in os.environ.items() if value is not None})
    return values


def seed_target(values: dict[str, str] | None = None) -> SeedTarget:
    values = values or load_environment_values()
    postgres_password = values.get("POSTGRES_PASSWORD", "edr-local-postgres")
    clickhouse_password = values.get("CLICKHOUSE_PASSWORD", "edr-local-clickhouse")
    postgres_port = values.get("POSTGRES_HOST_PORT", "55432")
    clickhouse_port = values.get("CLICKHOUSE_HTTP_HOST_PORT", "58123")
    dashboard_port = values.get("NGINX_HTTP_HOST_PORT", "8080")
    collector_port = values.get("NGINX_MTLS_HOST_PORT", "8443")
    return SeedTarget(
        environment=values.get("EDR_ENV", "local").strip().lower(),
        postgres_dsn=values.get(
            "EDR_POSTGRES_DSN",
            f"postgresql://edr:{postgres_password}@127.0.0.1:{postgres_port}/edr",
        ),
        clickhouse_dsn=values.get(
            "EDR_CLICKHOUSE_DSN",
            f"http://edr:{clickhouse_password}@127.0.0.1:{clickhouse_port}/edr",
        ),
        dashboard_base_url=values.get("EDR_DASHBOARD_BASE_URL", f"http://127.0.0.1:{dashboard_port}"),
        collector_base_url=values.get(
            "EDR_COLLECTOR_BASE_URL",
            f"https://127.0.0.1:{collector_port}/api/v1/collector",
        ),
        allowed_qa_hosts=parse_allowed_qa_hosts(values.get("EDR_SEED_ALLOWED_QA_HOSTS")),
        production_demo_reset_mode=values.get("EDR_PRODUCTION_DEMO_RESET_MODE", ""),
        demo_reset_target_id=values.get("EDR_DEMO_RESET_TARGET_ID", ""),
        kafka_bootstrap_servers=values.get("EDR_KAFKA_BOOTSTRAP_SERVERS", ""),
        kafka_raw_topic=values.get("EDR_KAFKA_RAW_TOPIC", ""),
        kafka_validated_topic=values.get("EDR_KAFKA_VALIDATED_TOPIC", ""),
        event_storage_consumer_group=values.get("EDR_EVENT_STORAGE_CONSUMER_GROUP", ""),
        detection_consumer_group=values.get("EDR_DETECTION_CONSUMER_GROUP", ""),
        s3_bucket=values.get("EDR_S3_BUCKET", ""),
    )


def assert_safe_reset_target(target: SeedTarget) -> None:
    assert_safe_reset_targets(
        environment=target.environment,
        targets=_reset_targets(target),
        allowed_qa_hosts=target.allowed_qa_hosts,
    )


def _reset_targets(target: SeedTarget) -> tuple[tuple[str, str], tuple[str, str]]:
    return (("PostgreSQL", target.postgres_dsn), ("ClickHouse", target.clickhouse_dsn))


def _production_runtime_context(target: SeedTarget) -> dict[str, str]:
    return {
        "kafkaBootstrapServers": target.kafka_bootstrap_servers,
        "kafkaRawTopic": target.kafka_raw_topic,
        "kafkaValidatedTopic": target.kafka_validated_topic,
        "eventStorageConsumerGroup": target.event_storage_consumer_group,
        "detectionConsumerGroup": target.detection_consumer_group,
        "s3Bucket": target.s3_bucket,
    }


def production_demo_fingerprint(target: SeedTarget) -> str:
    return production_demo_target_fingerprint(
        environment=target.environment,
        targets=_reset_targets(target),
        reset_mode=target.production_demo_reset_mode,
        target_id=target.demo_reset_target_id,
        runtime_context=_production_runtime_context(target),
    )


def describe_target(target: SeedTarget) -> dict[str, str]:
    postgres = urlparse(target.postgres_dsn)
    clickhouse = urlparse(target.clickhouse_dsn)
    return {
        "environment": target.environment,
        "postgres": f"{postgres.hostname}:{postgres.port or 5432}/{database_name(target.postgres_dsn)}",
        "clickhouse": f"{clickhouse.hostname}:{clickhouse.port or 8123}/{database_name(target.clickhouse_dsn)}",
    }


def _stable_uuid(plan: str, seed: int, anchor: datetime, hostname: str, index: int, kind: str) -> UUID:
    name = f"edr-c:{plan}:{seed}:{_rfc3339(anchor)}:{hostname}:{index}:{kind}"
    return uuid5(NAMESPACE_URL, name)


def _event(
    profile: str,
    seed: int,
    anchor: datetime,
    hostname: str,
    index: int,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, object],
) -> EventPlan:
    return EventPlan(
        hostname=hostname,
        event_id=_stable_uuid(profile, seed, anchor, hostname, index, "event"),
        batch_id=_stable_uuid(profile, seed, anchor, hostname, index, "batch"),
        event_type=event_type,
        occurred_at=occurred_at,
        payload=payload,
    )


def _background_payload(event_type: str, endpoint: EndpointPlan, index: int) -> dict[str, object]:
    profiles = {
        "geonha-mac": {
            "processes": ("Code", "Terminal", "Docker Desktop", "python3", "node"),
            "commands": ("code .", "git status", "docker compose ps", "uv run pytest", "npm run dev"),
            "domains": ("github.com", "docs.python.org", "registry.npmjs.org", "hub.docker.com", "localhost"),
            "files": (
                "/Users/geonha/Developer/team-C/backend/main.py",
                "/Users/geonha/Developer/team-C/frontend/src/App.tsx",
                "/Users/geonha/Developer/team-C/pyproject.toml",
                "/Users/geonha/Documents/lecture/security-notes.md",
                "/Users/geonha/Developer/team-C/README.md",
            ),
            "user": "geonha",
        },
        "geonha-win": {
            "processes": ("Code.exe", "powershell.exe", "chrome.exe", "Docker Desktop.exe", "wsl.exe"),
            "commands": (
                "code .",
                "powershell.exe -NoProfile",
                "chrome.exe --profile-directory=Default",
                "docker compose ps",
                "wsl.exe",
            ),
            "domains": ("class.tukorea.ac.kr", "github.com", "notion.so", "discord.com", "learn.microsoft.com"),
            "files": (
                r"C:\Users\Geonha\Documents\TUKorea\network-assignment.md",
                r"C:\Users\Geonha\Desktop\team-C\backend\main.py",
                r"C:\Users\Geonha\Desktop\team-C\frontend\src\App.tsx",
                r"C:\Users\Geonha\Documents\TUKorea\capstone-notes.docx",
                r"C:\Users\Geonha\Downloads\lecture-week-14.pdf",
            ),
            "user": r"TUKOREA\geonha",
        },
        "soyeon": {
            "processes": ("chrome.exe", "Discord.exe", "MinecraftLauncher.exe", "javaw.exe", "Code.exe"),
            "commands": (
                "chrome.exe --profile-directory=Default",
                "Discord.exe --start-minimized",
                "MinecraftLauncher.exe",
                "javaw.exe -Xmx4G -jar minecraft.jar",
                "code .",
            ),
            "domains": ("class.tukorea.ac.kr", "discord.com", "minecraft.net", "github.com", "stackoverflow.com"),
            "files": (
                r"C:\Users\Soyeon\Documents\TUKorea\java-lab\Main.java",
                r"C:\Users\Soyeon\AppData\Roaming\.minecraft\options.txt",
                r"C:\Users\Soyeon\Documents\TUKorea\database-assignment.sql",
                r"C:\Users\Soyeon\Downloads\lecture-operating-system.pdf",
                r"C:\Users\Soyeon\Documents\TUKorea\algorithm-study.md",
            ),
            "user": r"TUKOREA\soyeon",
        },
        "hyeryeong": {
            "processes": ("Figma.exe", "Photoshop.exe", "Illustrator.exe", "chrome.exe", "Creative Cloud.exe"),
            "commands": (
                "Figma.exe --app-startup",
                "Photoshop.exe",
                "Illustrator.exe",
                "chrome.exe --profile-directory=Design",
                "Creative Cloud.exe --background",
            ),
            "domains": ("figma.com", "behance.net", "fonts.google.com", "pinterest.com", "creativecloud.adobe.com"),
            "files": (
                r"C:\Users\Hyeryeong\Documents\Design\mobile-app-wireframe.fig",
                r"C:\Users\Hyeryeong\Documents\Design\poster-final.psd",
                r"C:\Users\Hyeryeong\Documents\Design\brand-logo.ai",
                r"C:\Users\Hyeryeong\Downloads\pretendard-font.zip",
                r"C:\Users\Hyeryeong\Pictures\reference-board.png",
            ),
            "user": r"TUKOREA\hyeryeong",
        },
        "juho": {
            "processes": ("idea64.exe", "java.exe", "gradle.exe", "Docker Desktop.exe", "Postman.exe"),
            "commands": (
                "idea64.exe",
                "java.exe -jar build/libs/course-api.jar",
                "gradle.exe test",
                "docker compose up -d",
                "Postman.exe",
            ),
            "domains": (
                "class.tukorea.ac.kr",
                "github.com",
                "repo.maven.apache.org",
                "hub.docker.com",
                "learning.postman.com",
            ),
            "files": (
                r"C:\Users\Juho\IdeaProjects\course-api\src\main\java\Application.java",
                r"C:\Users\Juho\IdeaProjects\course-api\build.gradle",
                r"C:\Users\Juho\Documents\TUKorea\network-lab.pkt",
                r"C:\Users\Juho\Documents\TUKorea\api-test.postman_collection.json",
                r"C:\Users\Juho\Downloads\spring-week-14.pdf",
            ),
            "user": r"TUKOREA\juho",
        },
        "generic": {
            "processes": ("launchd", "chrome.exe"),
            "commands": ("/sbin/launchd", "chrome.exe"),
            "domains": ("docs.example.test",),
            "files": ("/tmp/lesson.txt",),
            "user": "student",
        },
    }
    profile = profiles[endpoint.activity_profile]
    position = index % len(profile["processes"])
    process = profile["processes"][position]
    command = profile["commands"][position]
    domain = profile["domains"][index % len(profile["domains"])]
    file_path = profile["files"][index % len(profile["files"])]
    if event_type == "PROCESS_EXECUTION":
        return {
            "processName": process,
            "processPath": f"/Applications/{process}.app/Contents/MacOS/{process}"
            if endpoint.os_type == "MACOS"
            else rf"C:\Program Files\{process}",
            "pid": 2000 + index,
            "ppid": 1000 + index,
            "commandLine": command,
            "userName": profile["user"],
        }
    if event_type == "NETWORK_CONNECTION":
        return {
            "protocol": "TCP",
            "remoteIp": f"192.0.2.{20 + index % 100}",
            "remotePort": 443,
            "remoteDomain": domain,
            "processName": process,
            "pid": 2000 + index,
        }
    if event_type == "FILE_EVENT":
        return {
            "filePath": file_path,
            "action": "MODIFY",
            "sha256": f"{index % 16:x}" * 64,
            "processName": process,
            "pid": 2000 + index,
        }
    if event_type == "DNS_QUERY":
        return {
            "query": domain,
            "recordType": "A",
            "responseCode": "NOERROR",
            "answers": [f"198.51.100.{20 + index % 100}"],
            "processName": process,
            "pid": 2000 + index,
        }
    return {
        "l7Protocol": "HTTPS",
        "httpMethod": "GET",
        "httpHost": domain,
        "url": f"https://{domain}/activity/{index % 20}",
        "httpStatusCode": 200,
        "httpUserAgent": "Mozilla/5.0 Chrome/126.0",
        "tlsSni": domain,
        "tlsVersion": "TLS1.3",
    }


def _daily_background_events(
    profile: str,
    seed: int,
    anchor: datetime,
    endpoint: EndpointPlan,
    daily_counts: tuple[int, ...],
    *,
    first_index: int = 0,
    newest_end_at: datetime | None = None,
) -> list[EventPlan]:
    event_types = ("PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT", "DNS_QUERY", "L7_EVENT")
    events: list[EventPlan] = []
    index = first_index
    for day_offset, count in enumerate(daily_counts):
        start = anchor - timedelta(days=day_offset + 1)
        end = newest_end_at if day_offset == 0 and newest_end_at is not None else anchor - timedelta(days=day_offset)
        span = end - start
        for position in range(count):
            ratio = (position + 1) / (count + 1)
            occurred_at = start + span * ratio
            event_type = event_types[index % len(event_types)]
            events.append(
                _event(
                    profile,
                    seed,
                    anchor,
                    endpoint.hostname,
                    index,
                    event_type,
                    occurred_at,
                    _background_payload(event_type, endpoint, index),
                )
            )
            index += 1
    return events


def build_presentation_plan(seed: int, anchor: datetime) -> ProfilePlan:
    endpoints = (
        EndpointPlan(
            "GEONHA-MACMINI",
            "geonha-macmini",
            "MACOS",
            "macOS 15.5",
            "192.0.2.10",
            "ONLINE",
            1_400,
            "ARM64",
            "황건하",
            "컴퓨터공학전공",
            "geonha-mac",
        ),
        EndpointPlan(
            "GEONHA-WIN",
            "geonha-win",
            "WINDOWS",
            "Windows 11 24H2",
            "192.0.2.11",
            "OFFLINE",
            1_050,
            "X64",
            "황건하",
            "컴퓨터공학전공",
            "geonha-win",
        ),
        EndpointPlan(
            "SOYEON-WIN",
            "soyeon-win",
            "WINDOWS",
            "Windows 11 24H2",
            "192.0.2.20",
            "ONLINE",
            1_190,
            "X64",
            "박소연",
            "컴퓨터공학전공",
            "soyeon",
        ),
        EndpointPlan(
            "HYERYEONG-WIN",
            "hyeryeong-win",
            "WINDOWS",
            "Windows 11 24H2",
            "192.0.2.30",
            "ONLINE",
            910,
            "X64",
            "이혜령",
            "디자인전공",
            "hyeryeong",
            "DEGRADED",
        ),
        EndpointPlan(
            "JUHO-WIN",
            "juho-win",
            "WINDOWS",
            "Windows 11 24H2",
            "192.0.2.40",
            "ONLINE",
            1_050,
            "X64",
            "이주호",
            "컴퓨터공학전공",
            "juho",
        ),
    )
    epoch = int(anchor.timestamp())
    current_window = datetime.fromtimestamp((epoch // 1800) * 1800, tz=UTC)
    elapsed_seconds = (anchor - current_window).total_seconds()
    if elapsed_seconds < 6:
        window_start = current_window - timedelta(minutes=30)
        attack_offsets = tuple(timedelta(minutes=value) for value in (5, 7, 9, 10, 12, 14))
    elif elapsed_seconds >= 15 * 60:
        window_start = current_window
        attack_offsets = tuple(timedelta(minutes=value) for value in (5, 7, 9, 10, 12, 14))
    else:
        window_start = current_window
        spacing = elapsed_seconds / 7
        attack_offsets = tuple(timedelta(seconds=spacing * value) for value in range(1, 7))
    main = endpoints[2]
    daily_count = PRESENTATION_DAILY_EVENTS[main.hostname]
    events = _daily_background_events(
        "presentation",
        seed,
        anchor,
        main,
        (daily_count - 6,) + (daily_count,) * (PRESENTATION_DAYS - 1),
        first_index=6,
        newest_end_at=window_start - timedelta(minutes=1),
    )
    attack = (
        (
            0,
            "DNS_QUERY",
            attack_offsets[0],
            {
                "query": "minecraft-shader.example",
                "recordType": "A",
                "responseCode": "NOERROR",
                "answers": ["203.0.113.40"],
                "processName": "chrome.exe",
                "pid": 4100,
            },
        ),
        (
            1,
            "FILE_EVENT",
            attack_offsets[1],
            {
                "filePath": r"C:\Users\Soyeon\Downloads\Minecraft_Shader_Setup.exe",
                "action": "CREATE",
                "sha256": "7" * 64,
                "processName": "chrome.exe",
                "pid": 4100,
            },
        ),
        (
            2,
            "PROCESS_EXECUTION",
            attack_offsets[2],
            {
                "processName": "Minecraft_Shader_Setup.exe",
                "processPath": r"C:\Users\Soyeon\Downloads\Minecraft_Shader_Setup.exe",
                "pid": 4200,
                "ppid": 4100,
                "commandLine": r"C:\Users\Soyeon\Downloads\Minecraft_Shader_Setup.exe --install",
                "userName": r"TUKOREA\soyeon",
            },
        ),
        (
            3,
            "PROCESS_EXECUTION",
            attack_offsets[3],
            {
                "processName": "powershell.exe",
                "processPath": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                "pid": 4242,
                "ppid": 4200,
                "commandLine": "powershell.exe -NoProfile -EncodedCommand SAFEDEMOONE",
                "userName": r"TUKOREA\soyeon",
            },
        ),
        (
            4,
            "PROCESS_EXECUTION",
            attack_offsets[4],
            {
                "processName": "powershell.exe",
                "processPath": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                "pid": 4243,
                "ppid": 4242,
                "commandLine": "powershell.exe -NoProfile -EncodedCommand SAFEDEMOTWO",
                "userName": r"TUKOREA\soyeon",
            },
        ),
        (
            5,
            "L7_EVENT",
            attack_offsets[5],
            {
                "l7Protocol": "TLS",
                "tlsSni": "update-cache.test",
                "tlsVersion": "TLS1.2",
            },
        ),
    )
    events.extend(
        _event(
            "presentation",
            seed,
            anchor,
            main.hostname,
            index,
            event_type,
            window_start + offset,
            payload,
        )
        for index, event_type, offset, payload in attack
    )
    for endpoint in endpoints:
        if endpoint.hostname == main.hostname:
            continue
        endpoint_daily_count = PRESENTATION_DAILY_EVENTS[endpoint.hostname]
        events.extend(
            _daily_background_events(
                "presentation",
                seed,
                anchor,
                endpoint,
                (endpoint_daily_count,) * PRESENTATION_DAYS,
            )
        )
    plan = ProfilePlan(
        "presentation",
        seed,
        anchor,
        endpoints,
        tuple(sorted(events, key=lambda item: (item.occurred_at, str(item.event_id)))),
    )
    _validate_plan(plan)
    return plan


def build_dns_correctness_plan(seed: int, anchor: datetime) -> ProfilePlan:
    endpoints = (
        EndpointPlan(
            "DEMO-DNS-WIN-01", "presentation-dns-win-01", "WINDOWS", "Windows 11 24H2", "192.0.2.61", "ONLINE", 4, "X64"
        ),
        EndpointPlan(
            "DEMO-DNS-MAC-02", "presentation-dns-mac-02", "MACOS", "macOS 15.5", "192.0.2.62", "ONLINE", 4, "ARM64"
        ),
    )
    rows = (
        (
            endpoints[0],
            "NETWORK_CONNECTION",
            {
                "protocol": "TCP",
                "remoteIp": "203.0.113.10",
                "remotePort": 443,
                "remoteDomain": "yahoo.com",
                "processName": "chrome.exe",
                "pid": 6101,
            },
        ),
        (
            endpoints[0],
            "L7_EVENT",
            {
                "l7Protocol": "HTTPS",
                "httpMethod": "GET",
                "httpHost": "mail.yahoo.com",
                "url": "https://mail.yahoo.com/inbox",
                "tlsSni": "mail.yahoo.com",
                "tlsVersion": "TLS1.3",
            },
        ),
        (
            endpoints[0],
            "DNS_QUERY",
            {
                "query": "api.yahoo.com",
                "recordType": "A",
                "responseCode": "NOERROR",
                "answers": ["203.0.113.10", "203.0.113.11"],
                "processName": "chrome.exe",
                "pid": 6101,
            },
        ),
        (
            endpoints[0],
            "L7_EVENT",
            {
                "l7Protocol": "HTTPS",
                "httpMethod": "GET",
                "httpHost": "docs.example.test",
                "url": "https://docs.example.test/",
                "tlsSni": "notyahoo.com",
                "tlsVersion": "TLS1.3",
            },
        ),
        (
            endpoints[1],
            "L7_EVENT",
            {
                "l7Protocol": "HTTPS",
                "httpMethod": "GET",
                "httpHost": "yahoo.com.evil.example",
                "url": "https://yahoo.com.evil.example/",
                "tlsSni": "yahoo.com.evil.example",
                "tlsVersion": "TLS1.3",
            },
        ),
        (
            endpoints[1],
            "NETWORK_CONNECTION",
            {
                "protocol": "TCP",
                "remoteIp": "203.0.113.12",
                "remotePort": 443,
                "remoteDomain": "yahoo.co",
                "processName": "launchd",
                "pid": 6201,
            },
        ),
        (
            endpoints[1],
            "DNS_QUERY",
            {
                "query": "answers.example.test",
                "recordType": "A",
                "responseCode": "NOERROR",
                "answers": ["203.0.113.10", "203.0.113.11"],
                "processName": "launchd",
                "pid": 6201,
            },
        ),
        (
            endpoints[1],
            "PROCESS_EXECUTION",
            {
                "processName": "launchd",
                "processPath": "/sbin/launchd",
                "pid": 1,
                "ppid": 0,
                "commandLine": "/sbin/launchd",
                "userName": "root",
            },
        ),
    )
    events = tuple(
        _event(
            "dns-correctness",
            seed,
            anchor,
            endpoint.hostname,
            index,
            event_type,
            anchor - timedelta(minutes=40 - index * 3),
            payload,
        )
        for index, (endpoint, event_type, payload) in enumerate(rows)
    )
    plan = ProfilePlan("dns-correctness", seed, anchor, endpoints, events)
    _validate_plan(plan)
    return plan


def build_plan(profile: str, seed: int, anchor: datetime) -> ProfilePlan:
    if profile == "presentation":
        return build_presentation_plan(seed, anchor)
    if profile == "dns-correctness":
        return build_dns_correctness_plan(seed, anchor)
    raise ValueError(f"unsupported profile: {profile}")


@lru_cache(maxsize=1)
def _load_detection_engine() -> DetectionEngine:
    loader = RuleLoader(
        schema_path=ROOT / "schemas" / "rule-v1.schema.json",
        mapping_path=ROOT / "mappings" / "mitre_attack.yaml",
    )
    return DetectionEngine(loader.load_directory(ROOT / "rules"))


def _raw_event(plan: EventPlan, endpoint: EndpointPlan, endpoint_id: int) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "batchId": str(plan.batch_id),
        "endpointId": endpoint_id,
        "agentId": endpoint.agent_id,
        "hostname": endpoint.hostname,
        "osType": endpoint.os_type,
        "ipAddress": endpoint.ip_address,
        "event": {
            "eventId": str(plan.event_id),
            "eventType": plan.event_type,
            "occurredAt": _rfc3339(plan.occurred_at),
            "payload": plan.payload,
        },
    }


def _normalized_events(plan: ProfilePlan, endpoint_ids: dict[str, int]) -> list[dict[str, object]]:
    endpoints = {item.hostname: item for item in plan.endpoints}
    return [
        normalize_event(
            _raw_event(item, endpoints[item.hostname], endpoint_ids[item.hostname]),
            ingested_at=item.occurred_at + timedelta(seconds=30),
        )
        for item in plan.events
    ]


def _validate_plan(plan: ProfilePlan) -> None:
    expected = {"presentation": (5, 5_600, 3, 1), "dns-correctness": (2, 8, 0, 0)}[plan.profile]
    if (len(plan.endpoints), len(plan.events), plan.counts["alerts"], plan.counts["incidents"]) != expected:
        raise RuntimeError(f"{plan.profile} plan count contract changed")
    if Counter(item.hostname for item in plan.events) != Counter(
        {item.hostname: item.event_count for item in plan.endpoints}
    ):
        raise RuntimeError(f"{plan.profile} Endpoint event distribution changed")
    synthetic_ids = {item.hostname: index + 1 for index, item in enumerate(plan.endpoints)}
    matches = [
        match
        for event in _normalized_events(plan, synthetic_ids)
        for match in _load_detection_engine().evaluate(event, detected_at=event["ingested_at"])
    ]
    if len(matches) != plan.counts["alerts"]:
        raise RuntimeError(f"{plan.profile} produces {len(matches)} Rule matches, expected {plan.counts['alerts']}")
    if plan.profile == "presentation":
        latest_24h = sum(event.occurred_at > plan.anchor - timedelta(days=1) for event in plan.events)
        latest_7d = sum(event.occurred_at > plan.anchor - timedelta(days=7) for event in plan.events)
        if (latest_24h, latest_7d) != (400, 2_800):
            raise RuntimeError(
                f"presentation rolling window contract changed: latest24h={latest_24h}, latest7d={latest_7d}"
            )
        codes = Counter(match.alert.rule_code for match in matches)
        keys = Counter(match.incident.correlation_key for match in matches if match.incident is not None)
        windows = {match.incident.window_start_at for match in matches if match.incident is not None}
        if codes != {"PROC_POWERSHELL_ENCODED": 2, "NET_SUSPICIOUS_EGRESS": 1}:
            raise RuntimeError(f"presentation Rule matches changed: {dict(codes)}")
        if keys != {"powershell-tls-egress-chain": 3} or len(windows) != 1:
            raise RuntimeError("presentation Incident correlation contract changed")


def _reset_databases(
    target: SeedTarget,
    *,
    confirm_reset: bool = False,
    production_demo_reset: bool = False,
    production_confirmation: str | None = None,
    runtime_stopped_confirmation: str | None = None,
    target_fingerprint: str | None = None,
) -> None:
    require_reset_confirmation(confirm_reset)
    if production_demo_reset:
        assert_production_demo_reset_authorized(
            environment=target.environment,
            targets=_reset_targets(target),
            reset_mode=target.production_demo_reset_mode,
            target_id=target.demo_reset_target_id,
            runtime_context=_production_runtime_context(target),
            confirmation=production_confirmation,
            runtime_stopped_confirmation=runtime_stopped_confirmation,
            target_fingerprint=target_fingerprint,
        )
    else:
        assert_safe_reset_target(target)
    with psycopg.connect(target.postgres_dsn) as connection:
        apply_postgres_migrations(connection, ROOT / "migrations" / "postgresql", direction="down")
        apply_postgres_migrations(connection, ROOT / "migrations" / "postgresql")
        record_applied_postgres_migrations(connection, ROOT / "migrations" / "postgresql")
    clickhouse = clickhouse_connect.get_client(dsn=target.clickhouse_dsn, autogenerate_session_id=False)
    try:
        clickhouse_migrations = ROOT / "migrations" / "clickhouse"
        for path in sorted(clickhouse_migrations.glob("*.down.sql"), reverse=True):
            _apply_clickhouse_down_file(clickhouse, path)
        for path in sorted(clickhouse_migrations.glob("*.up.sql")):
            apply_clickhouse_file(clickhouse, path)
    finally:
        clickhouse.close()


def _apply_clickhouse_down_file(client: ClickHouseCommandClient, path: Path) -> None:
    for statement in split_sql_statements(path.read_text(encoding="utf-8")):
        try:
            client.command(statement)
        except ClickHouseError as error:
            message = str(error)
            is_unknown_table = (
                re.search(r"\bcode\s*:\s*60\b", message, flags=re.IGNORECASE) is not None
                and re.search(r"\bUNKNOWN_TABLE\b", message) is not None
            )
            if not is_unknown_table:
                raise


def _seed_users(connection: psycopg.Connection, now: datetime) -> None:
    UserRepository(connection).create_admin(
        login_id="frontend-admin",
        name="Presentation Administrator",
        password_hash=hash_password("frontend-admin-password"),
        now=now,
    )
    connection.execute(
        """
        INSERT INTO users (login_id, password_hash, name, role, status, locale, created_at, updated_at)
        VALUES (%s, %s, %s, 'VIEWER', 'ACTIVE', 'KO', %s, %s)
        """,
        ("frontend-viewer", hash_password("frontend-viewer-password"), "Presentation Viewer", now, now),
    )
    connection.commit()


def _insert_endpoints(connection: psycopg.Connection, plan: ProfilePlan) -> dict[str, int]:
    repository = EndpointRepository(connection)
    endpoint_ids: dict[str, int] = {}
    for endpoint in plan.endpoints:
        metadata = agent_fixture_metadata(endpoint)
        endpoint_id = repository.insert(
            EndpointInsert(
                agent_id=endpoint.agent_id,
                hostname=endpoint.hostname,
                os_type=OsType(endpoint.os_type),
                registered_at=plan.anchor - timedelta(days=45),
            )
        )
        connection.execute(
            """
            UPDATE endpoints SET
                os_version = %s, ip_address = %s, agent_version = %s, agent_build_id = %s,
                agent_arch = %s, capability_codes_json = %s, sensor_health_json = %s,
                status = %s, last_seen_at = %s, updated_at = %s
            WHERE endpoint_id = %s
            """,
            (
                endpoint.os_version,
                endpoint.ip_address,
                metadata.version,
                metadata.build_id,
                endpoint.agent_arch,
                Jsonb(list(metadata.capability_codes)),
                Jsonb(list(metadata.sensor_health)),
                endpoint.status,
                plan.anchor - timedelta(hours=6) if endpoint.status == "OFFLINE" else plan.anchor,
                plan.anchor,
                endpoint_id,
            ),
        )
        connection.commit()
        endpoint_ids[endpoint.hostname] = endpoint_id
    return endpoint_ids


def _insert_hot_metadata(connection: psycopg.Connection, events: list[dict[str, object]], now: datetime) -> None:
    counts = Counter(
        (
            int(event["endpoint_id"]),
            event["occurred_at"].astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0),
        )
        for event in events
    )
    for (endpoint_id, start), count in sorted(counts.items()):
        connection.execute(
            """
            INSERT INTO ingest_metadata (
                endpoint_id, bucket_start_at, bucket_end_at, storage_backend, storage_class,
                storage_status, storage_path, event_count, created_at, updated_at
            ) VALUES (%s, %s, %s, 'CLICKHOUSE', 'HOT', 'HOT', %s, %s, %s, %s)
            ON CONFLICT (endpoint_id, bucket_start_at, storage_backend, storage_class) DO UPDATE SET
                event_count = EXCLUDED.event_count, updated_at = EXCLUDED.updated_at, is_delete = FALSE
            """,
            (
                endpoint_id,
                start,
                start + timedelta(days=1),
                f"clickhouse://edr_events/date={start.date()}/endpoint_id={endpoint_id}",
                count,
                now,
                now,
            ),
        )
    connection.commit()


def _direct_seed(
    target: SeedTarget,
    plan: ProfilePlan,
    *,
    seed_default_users: bool = True,
) -> tuple[dict[str, int], dict[str, object]]:
    with psycopg.connect(target.postgres_dsn) as connection:
        if seed_default_users:
            _seed_users(connection, plan.anchor)
        endpoint_ids = _insert_endpoints(connection, plan)
    events = _normalized_events(plan, endpoint_ids)
    clickhouse = clickhouse_connect.get_client(dsn=target.clickhouse_dsn, autogenerate_session_id=False)
    try:
        EventRepository(clickhouse).insert(events)
    finally:
        clickhouse.close()
    ids: dict[str, object] = {
        "endpointIdsByHostname": endpoint_ids,
        "presentationEndpointId": endpoint_ids.get("SOYEON-WIN"),
        "chainIncidentId": None,
        "powershellAlertIds": [],
        "egressAlertId": None,
        "eventIds": [str(event["event_id"]) for event in events],
    }
    engine = _load_detection_engine()
    with psycopg.connect(target.postgres_dsn) as connection:
        alerts = AlertRepository(connection)
        incidents = IncidentRepository(connection)
        for event in events:
            for match in engine.evaluate(event, detected_at=event["ingested_at"]):
                stored_alert = alerts.insert_if_absent(match.alert)
                if match.alert.rule_code == "PROC_POWERSHELL_ENCODED":
                    ids["powershellAlertIds"].append(stored_alert.alert_id)
                elif match.alert.rule_code == "NET_SUSPICIOUS_EGRESS":
                    ids["egressAlertId"] = stored_alert.alert_id
                if match.incident is None:
                    continue
                stored_incident = incidents.upsert(
                    IncidentInsert(
                        endpoint_id=match.incident.endpoint_id,
                        correlation_key=match.incident.correlation_key,
                        window_start_at=match.incident.window_start_at,
                        window_end_at=match.incident.window_end_at,
                        title=match.alert.title,
                        description=match.alert.summary,
                        severity=match.alert.severity,
                        detected_at=event["ingested_at"],
                    )
                )
                incidents.link_alert(
                    incident_id=stored_incident.incident_id,
                    alert_id=stored_alert.alert_id,
                    linked_at=event["ingested_at"],
                )
                ids["chainIncidentId"] = stored_incident.incident_id
        _insert_hot_metadata(connection, events, plan.anchor)
    return endpoint_ids, ids


def _collector_client(certificate: Path, private_key: Path, ca_certificate: Path) -> httpx.Client:
    context = ssl.create_default_context(cafile=str(ca_certificate))
    context.load_cert_chain(certfile=str(certificate), keyfile=str(private_key))
    return httpx.Client(verify=context, timeout=15)


def _collector_seed(
    target: SeedTarget,
    plan: ProfilePlan,
    *,
    wait_timeout_seconds: int,
    seed_default_users: bool = True,
) -> tuple[dict[str, int], dict[str, object]]:
    from tools.provision_agent_cert import provision

    authority = ROOT / "runtime" / "compose" / "cert-authority"
    if seed_default_users:
        with psycopg.connect(target.postgres_dsn) as connection:
            _seed_users(connection, plan.anchor)
    endpoint_ids: dict[str, int] = {}
    certificates = {}
    for endpoint in plan.endpoints:
        metadata = agent_fixture_metadata(endpoint)
        certificate = provision(endpoint.agent_id, authority)
        certificates[endpoint.hostname] = certificate
        with _collector_client(certificate.certificate, certificate.private_key, certificate.ca_certificate) as client:
            response = client.post(
                f"{target.collector_base_url}/agents/register",
                json={
                    "agentId": endpoint.agent_id,
                    "hostname": endpoint.hostname,
                    "osType": endpoint.os_type,
                    "osVersion": endpoint.os_version,
                    "agentVersion": metadata.version,
                    "agentBuildId": metadata.build_id,
                    "agentArch": endpoint.agent_arch,
                    "capabilityCodes": list(metadata.capability_codes),
                },
            )
            response.raise_for_status()
            endpoint_ids[endpoint.hostname] = int(response.json()["data"]["endpointId"])
            heartbeat = client.post(
                f"{target.collector_base_url}/agents/heartbeat",
                json={
                    "agentId": endpoint.agent_id,
                    "agentVersion": metadata.version,
                    "agentBuildId": metadata.build_id,
                    "agentArch": endpoint.agent_arch,
                    "capabilityCodes": list(metadata.capability_codes),
                    "bufferDepth": 0,
                    "sensorHealth": list(metadata.sensor_health),
                    "sentAt": _rfc3339(datetime.now(UTC)),
                },
            )
            heartbeat.raise_for_status()
    events_by_hostname: dict[str, list[EventPlan]] = {endpoint.hostname: [] for endpoint in plan.endpoints}
    for event in plan.events:
        events_by_hostname[event.hostname].append(event)
    accepted: list[str] = []
    for endpoint in plan.endpoints:
        certificate = certificates[endpoint.hostname]
        event_plans = events_by_hostname[endpoint.hostname]
        for batch_index, start in enumerate(range(0, len(event_plans), 100)):
            batch_events = event_plans[start : start + 100]
            batch_id = _stable_uuid(
                plan.profile,
                plan.seed,
                plan.anchor,
                endpoint.hostname,
                batch_index,
                "collector-batch",
            )
            with _collector_client(
                certificate.certificate,
                certificate.private_key,
                certificate.ca_certificate,
            ) as client:
                response = client.post(
                    f"{target.collector_base_url}/telemetry/batches",
                    json={
                        "schemaVersion": 1,
                        "batchId": str(batch_id),
                        "agentId": endpoint.agent_id,
                        "sentAt": _rfc3339(datetime.now(UTC)),
                        "events": [
                            {
                                "eventId": str(event.event_id),
                                "eventType": event.event_type,
                                "occurredAt": _rfc3339(event.occurred_at),
                                "payload": event.payload,
                            }
                            for event in batch_events
                        ],
                    },
                )
                response.raise_for_status()
                data = response.json()["data"]
                if data["rejectedEvents"]:
                    raise RuntimeError(f"Collector rejected presentation events: {data['rejectedEvents']}")
                accepted.extend(data["acceptedEventIds"])
    if len(accepted) != len(plan.events):
        raise RuntimeError(f"Collector acknowledged {len(accepted)} of {len(plan.events)} events")
    ids = _wait_for_pipeline(target, plan, endpoint_ids, wait_timeout_seconds)
    with psycopg.connect(target.postgres_dsn) as connection:
        for endpoint in plan.endpoints:
            connection.execute(
                "UPDATE endpoints SET status=%s, last_seen_at=%s, updated_at=%s WHERE endpoint_id=%s",
                (
                    endpoint.status,
                    plan.anchor - timedelta(hours=6) if endpoint.status == "OFFLINE" else plan.anchor,
                    plan.anchor,
                    endpoint_ids[endpoint.hostname],
                ),
            )
        connection.commit()
    ids["eventIds"] = accepted
    ids["endpointIdsByHostname"] = endpoint_ids
    ids["presentationEndpointId"] = endpoint_ids.get("SOYEON-WIN")
    return endpoint_ids, ids


def _wait_for_pipeline(
    target: SeedTarget,
    plan: ProfilePlan,
    endpoint_ids: dict[str, int],
    timeout_seconds: int,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    endpoint_values = list(endpoint_ids.values())
    while time.monotonic() < deadline:
        clickhouse = clickhouse_connect.get_client(dsn=target.clickhouse_dsn, autogenerate_session_id=False)
        try:
            result = clickhouse.query(
                """
                SELECT uniqExact(event_id)
                FROM edr_events FINAL
                WHERE endpoint_id IN {endpoint_ids:Array(UInt64)} AND is_delete=0
                """,
                parameters={"endpoint_ids": endpoint_values},
            )
            event_count = int(result.result_rows[0][0])
        finally:
            clickhouse.close()
        with psycopg.connect(target.postgres_dsn) as connection:
            alert_rows = connection.execute(
                "SELECT alert_id, rule_code FROM alerts WHERE is_delete=FALSE ORDER BY alert_id"
            ).fetchall()
            incident_rows = connection.execute(
                "SELECT incident_id, correlation_key FROM incidents WHERE is_delete=FALSE ORDER BY incident_id"
            ).fetchall()
        if (
            event_count == len(plan.events)
            and len(alert_rows) == plan.counts["alerts"]
            and len(incident_rows) == plan.counts["incidents"]
        ):
            powershell_alerts = [int(row[0]) for row in alert_rows if row[1] == "PROC_POWERSHELL_ENCODED"]
            egress_alert = next((int(row[0]) for row in alert_rows if row[1] == "NET_SUSPICIOUS_EGRESS"), None)
            chain_incident = next(
                (int(row[0]) for row in incident_rows if row[1] == "powershell-tls-egress-chain"), None
            )
            return {
                "chainIncidentId": chain_incident,
                "powershellAlertIds": powershell_alerts,
                "egressAlertId": egress_alert,
            }
        time.sleep(0.5)
    raise TimeoutError(f"Collector/Kafka pipeline did not reach expected counts within {timeout_seconds} seconds")


def _manifest(
    target: SeedTarget,
    plan: ProfilePlan,
    ingestion_mode: str,
    endpoint_ids: dict[str, int],
    ids: dict[str, object],
    *,
    reset_mode: str = "local-qa-full-reset",
    accounts_seeded: bool = True,
    target_fingerprint: str | None = None,
) -> dict[str, object]:
    event_times = [event.occurred_at for event in plan.events]
    main_endpoint_id = endpoint_ids.get("SOYEON-WIN")
    chain_incident_id = ids.get("chainIncidentId")
    egress_alert_id = ids.get("egressAlertId")
    time_range = (
        f"timePreset=CUSTOM&from={_rfc3339(min(event_times))}&to={_rfc3339(plan.anchor + timedelta(minutes=1))}"
    )
    return {
        "profile": plan.profile,
        "seed": plan.seed,
        "anchor": _rfc3339(plan.anchor),
        "generatedAt": _rfc3339(datetime.now(UTC)),
        "mockData": True,
        "dataNotice": "시연을 위해 재현한 데이터이며 production 실측값이 아닙니다.",
        "ingestionMode": ingestion_mode,
        "resetMode": reset_mode,
        "accountsSeeded": accounts_seeded,
        "accountProvisioningRequired": not accounts_seeded,
        "targetFingerprint": target_fingerprint,
        "timeRange": {"from": _rfc3339(min(event_times)), "to": _rfc3339(plan.anchor + timedelta(minutes=1))},
        "counts": plan.counts,
        "rangeCounts": {"latest24h": 400, "latest7d": 2_800, "latest14d": 5_600}
        if plan.profile == "presentation"
        else {"custom": len(plan.events)},
        "endpointProfiles": [
            {
                "hostname": endpoint.hostname,
                "ownerName": endpoint.owner_name,
                "major": endpoint.major,
                "osType": endpoint.os_type,
                "status": endpoint.status,
                "sensorStatus": endpoint.sensor_status,
                "dailyEvents": PRESENTATION_DAILY_EVENTS.get(endpoint.hostname),
                "totalEvents": endpoint.event_count,
            }
            for endpoint in plan.endpoints
        ],
        "ids": ids,
        "urls": {
            "overview": f"{target.dashboard_base_url}/?timePreset=LATEST_24H",
            "endpointDetail": f"{target.dashboard_base_url}/endpoints/{main_endpoint_id}" if main_endpoint_id else None,
            "endpointTimeline": f"{target.dashboard_base_url}/events?endpointId={main_endpoint_id}&{time_range}"
            if main_endpoint_id
            else None,
            "chainIncident": f"{target.dashboard_base_url}/incidents/{chain_incident_id}"
            if chain_incident_id
            else None,
            "egressAlert": f"{target.dashboard_base_url}/alerts/{egress_alert_id}" if egress_alert_id else None,
            "dnsCorrectness": f"{target.dashboard_base_url}/intelligence?value=yahoo.com&{time_range}",
        },
    }


def _manifest_output_path(path: Path | None, profile: str, *, production_demo_reset: bool) -> Path:
    if production_demo_reset:
        if path is None:
            raise ValueError("production demo reset requires an explicit --output-manifest path")
        if not path.is_absolute():
            raise ValueError("production demo manifest path must be absolute")
        resolved = path.resolve()
        allowed_root = Path("/tmp/edr-c-demo").resolve()
        if resolved == allowed_root or not resolved.is_relative_to(allowed_root):
            raise ValueError("production demo manifest must be written below /tmp/edr-c-demo")
        if resolved.exists() and not resolved.is_file():
            raise ValueError("production demo manifest target must be a regular file")
        return resolved
    selected = path or DEFAULT_MANIFESTS[profile]
    return (selected if selected.is_absolute() else ROOT / selected).resolve()


def _preflight_manifest_output(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_file():
        raise ValueError("manifest target must be a regular file")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    probe_descriptor = -1
    probe_path: Path | None = None
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write("manifest-write-preflight\n")
            handle.flush()
            os.fsync(handle.fileno())
        probe_descriptor, probe_name = tempfile.mkstemp(prefix=f".{path.name}.probe.", dir=path.parent)
        probe_path = Path(probe_name)
        os.close(probe_descriptor)
        probe_descriptor = -1
        os.replace(temporary_path, probe_path)
        if not probe_path.is_file():
            raise OSError("manifest atomic replace preflight did not create a regular file")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if probe_descriptor >= 0:
            os.close(probe_descriptor)
        temporary_path.unlink(missing_ok=True)
        if probe_path is not None:
            probe_path.unlink(missing_ok=True)


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def _print_plan(
    plan: ProfilePlan,
    target: SeedTarget,
    ingestion_mode: str,
    *,
    reset_mode: str,
    accounts_seeded: bool,
    target_fingerprint: str | None,
) -> None:
    target_description = describe_target(target)
    print(f"EDR_C {plan.profile} demo seed")
    print("  mock data:        yes (not production measurements)")
    print(f"  ingestion mode:   {ingestion_mode}")
    print(f"  reset mode:       {reset_mode}")
    print(f"  accounts seeded:  {'yes' if accounts_seeded else 'no'}")
    print(f"  anchor:           {_rfc3339(plan.anchor)}")
    print(f"  PostgreSQL:       {target_description['postgres']}")
    print(f"  ClickHouse:       {target_description['clickhouse']}")
    if target_fingerprint is not None:
        print(f"  target fingerprint: {target_fingerprint}")
    print(f"  Endpoints:        {plan.counts['endpoints']}")
    print(f"  Events:           {plan.counts['events']}")
    print(f"  Alerts:           {plan.counts['alerts']}")
    print(f"  Incidents:        {plan.counts['incidents']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset an explicitly authorized demo target and build deterministic EDR_C presentation fixtures."
    )
    parser.add_argument("--profile", choices=PROFILES, default="presentation")
    parser.add_argument("--seed", type=int, default=20_260_721)
    parser.add_argument("--anchor", default="now", help="'now' or an RFC 3339 timestamp")
    parser.add_argument("--dry-run", action="store_true", help="Print counts and target without changing databases.")
    parser.add_argument(
        "--confirm-reset", action="store_true", help="Required because PostgreSQL and ClickHouse are reset."
    )
    parser.add_argument("--output-manifest", type=Path)
    parser.add_argument(
        "--production-demo-reset",
        action="store_true",
        help="Use the separately guarded full-reset path for the dedicated production mentor demo.",
    )
    parser.add_argument(
        "--confirm-production-demo-reset",
        help=f"Production-only destructive confirmation. Exact value: {PRODUCTION_DEMO_RESET_CONFIRMATION}",
    )
    parser.add_argument(
        "--confirm-runtime-stopped",
        help=f"Confirms that ingress and workers are stopped. Exact value: {PRODUCTION_RUNTIME_STOPPED_CONFIRMATION}",
    )
    parser.add_argument(
        "--target-fingerprint",
        help="Production-only SHA-256 target fingerprint printed by --dry-run.",
    )
    parser.add_argument(
        "--emit-through-collector",
        action="store_true",
        help="Use mTLS Collector -> Kafka -> Workers instead of direct repositories.",
    )
    parser.add_argument("--wait-timeout-seconds", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        anchor = parse_anchor(args.anchor)
        if args.wait_timeout_seconds < 1:
            raise ValueError("wait-timeout-seconds must be at least 1")
        plan = build_plan(args.profile, args.seed, anchor)
        target = seed_target()
        production_demo_reset = bool(args.production_demo_reset)
        if production_demo_reset and args.profile != "presentation":
            raise ValueError("production demo reset supports only the presentation profile")
        if production_demo_reset and args.emit_through_collector:
            raise ValueError("production demo reset supports only deterministic direct seed mode")
        mode = "collector-kafka" if args.emit_through_collector else "direct-seed"
        reset_mode = "production-demo-full-reset" if production_demo_reset else "local-qa-full-reset"
        accounts_seeded = not production_demo_reset
        fingerprint = production_demo_fingerprint(target) if production_demo_reset else None
        manifest_path = _manifest_output_path(
            args.output_manifest,
            args.profile,
            production_demo_reset=production_demo_reset,
        )
        _print_plan(
            plan,
            target,
            mode,
            reset_mode=reset_mode,
            accounts_seeded=accounts_seeded,
            target_fingerprint=fingerprint,
        )
        if args.dry_run:
            return 0
        if not args.confirm_reset:
            parser.error("--confirm-reset is required because this command resets PostgreSQL and ClickHouse")
        if production_demo_reset:
            assert_production_demo_reset_authorized(
                environment=target.environment,
                targets=_reset_targets(target),
                reset_mode=target.production_demo_reset_mode,
                target_id=target.demo_reset_target_id,
                runtime_context=_production_runtime_context(target),
                confirmation=args.confirm_production_demo_reset,
                runtime_stopped_confirmation=args.confirm_runtime_stopped,
                target_fingerprint=args.target_fingerprint,
            )
        _preflight_manifest_output(manifest_path)
        _reset_databases(
            target,
            confirm_reset=args.confirm_reset,
            production_demo_reset=production_demo_reset,
            production_confirmation=args.confirm_production_demo_reset,
            runtime_stopped_confirmation=args.confirm_runtime_stopped,
            target_fingerprint=args.target_fingerprint,
        )
        if args.emit_through_collector:
            endpoint_ids, ids = _collector_seed(
                target,
                plan,
                wait_timeout_seconds=args.wait_timeout_seconds,
                seed_default_users=accounts_seeded,
            )
        else:
            endpoint_ids, ids = _direct_seed(target, plan, seed_default_users=accounts_seeded)
        manifest = _manifest(
            target,
            plan,
            mode,
            endpoint_ids,
            ids,
            reset_mode=reset_mode,
            accounts_seeded=accounts_seeded,
            target_fingerprint=fingerprint,
        )
        _write_manifest(manifest_path, manifest)
        print(f"Manifest: {manifest_path}")
        if accounts_seeded:
            print("ADMIN  frontend-admin / frontend-admin-password")
            print("VIEWER frontend-viewer / frontend-viewer-password")
        else:
            print("Accounts: none; create the user-selected ADMIN separately with tools.create_admin")
        return 0
    except ClickHouseError:
        print("presentation demo seed failed: ClickHouse operation failed", file=os.sys.stderr)
        return 2
    except (RuntimeError, ValueError, OSError, psycopg.Error, httpx.HTTPError, TimeoutError) as error:
        print(f"presentation demo seed failed: {error}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
