"""Shared guardrails for destructive local and QA seed tools."""

import hashlib
import json
import re
import secrets
from collections.abc import Iterable, Mapping
from urllib.parse import unquote, urlparse

LOCAL_RESET_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "postgres", "clickhouse"})
ALLOWED_RESET_DATABASES = frozenset({"edr", "edr_qa", "test_edr"})
ALLOWED_RESET_ENVIRONMENTS = frozenset({"local", "qa"})
PRODUCTION_DEMO_RESET_CONFIRMATION = "FULL_RESET_DEDICATED_MENTOR_DEMO"
PRODUCTION_RUNTIME_STOPPED_CONFIRMATION = "INGRESS_AND_WORKERS_STOPPED"
PRODUCTION_DEMO_TARGET_ID_PATTERN = re.compile(r"^mentor-demo-[a-z0-9][a-z0-9._-]{7,51}$")
PRODUCTION_DEMO_TARGETS = {
    "PostgreSQL": ("postgresql", "postgres", 5432, "edr"),
    "ClickHouse": ("http", "clickhouse", 8123, "edr"),
}


def parse_allowed_qa_hosts(value: str | None) -> frozenset[str]:
    """Parse an exact, comma-separated remote QA host allowlist."""
    if not value:
        return frozenset()
    hosts = frozenset(host.strip().lower().rstrip(".") for host in value.split(",") if host.strip())
    if any("*" in host for host in hosts):
        raise ValueError("EDR_SEED_ALLOWED_QA_HOSTS does not support wildcards")
    return hosts


def database_name(dsn: str) -> str:
    parsed = urlparse(dsn)
    return unquote(parsed.path.strip("/").split("/", 1)[0])


def require_reset_confirmation(confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError("destructive seed requires explicit --confirm-reset confirmation")


def production_demo_target_descriptor(
    *,
    environment: str,
    targets: Iterable[tuple[str, str]],
    reset_mode: str,
    target_id: str,
    runtime_context: Mapping[str, str],
) -> dict[str, object]:
    if environment.strip().lower() != "production":
        raise RuntimeError("production demo reset requires EDR_ENV=production")
    if reset_mode != PRODUCTION_DEMO_RESET_CONFIRMATION:
        raise RuntimeError("production demo reset requires an explicit environment opt-in")
    normalized_target_id = target_id.strip().lower()
    if PRODUCTION_DEMO_TARGET_ID_PATTERN.fullmatch(normalized_target_id) is None:
        raise RuntimeError("EDR_DEMO_RESET_TARGET_ID must be a unique mentor-demo-* deployment identifier")
    expected_runtime_keys = {
        "kafkaBootstrapServers",
        "kafkaRawTopic",
        "kafkaValidatedTopic",
        "eventStorageConsumerGroup",
        "detectionConsumerGroup",
        "s3Bucket",
    }
    if set(runtime_context) != expected_runtime_keys:
        raise RuntimeError("production demo reset runtime context is incomplete")
    normalized_runtime_context = {key: value.strip() for key, value in runtime_context.items()}
    if any(not value or "<" in value or ">" in value for value in normalized_runtime_context.values()):
        raise RuntimeError("production demo reset runtime context contains an empty or placeholder value")

    descriptor_targets: dict[str, dict[str, object]] = {}
    provided_targets = tuple(targets)
    if len(provided_targets) != len(PRODUCTION_DEMO_TARGETS) or {
        label for label, _ in provided_targets
    } != set(PRODUCTION_DEMO_TARGETS):
        raise RuntimeError("production demo reset requires exact PostgreSQL and ClickHouse targets")

    for label, dsn in provided_targets:
        parsed = urlparse(dsn)
        expected_scheme, expected_host, expected_port, expected_database = PRODUCTION_DEMO_TARGETS[label]
        host = (parsed.hostname or "").lower().rstrip(".")
        database = database_name(dsn)
        if (
            parsed.scheme != expected_scheme
            or host != expected_host
            or parsed.port != expected_port
            or database != expected_database
            or parsed.path != f"/{expected_database}"
            or not parsed.username
            or parsed.password is None
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError(
                f"{label} is not the dedicated production demo target "
                f"({expected_scheme}://<user>@{expected_host}:{expected_port}/{expected_database})"
            )
        descriptor_targets[label] = {
            "scheme": parsed.scheme,
            "username": unquote(parsed.username),
            "host": host,
            "port": parsed.port,
            "database": database,
        }

    return {
        "version": 1,
        "purpose": "mentor-demo-full-reset",
        "environment": "production",
        "targetId": normalized_target_id,
        "targets": descriptor_targets,
        "runtime": normalized_runtime_context,
    }


def production_demo_target_fingerprint(
    *,
    environment: str,
    targets: Iterable[tuple[str, str]],
    reset_mode: str,
    target_id: str,
    runtime_context: Mapping[str, str],
) -> str:
    descriptor = production_demo_target_descriptor(
        environment=environment,
        targets=targets,
        reset_mode=reset_mode,
        target_id=target_id,
        runtime_context=runtime_context,
    )
    canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assert_production_demo_reset_authorized(
    *,
    environment: str,
    targets: Iterable[tuple[str, str]],
    reset_mode: str,
    target_id: str,
    runtime_context: Mapping[str, str],
    confirmation: str | None,
    runtime_stopped_confirmation: str | None,
    target_fingerprint: str | None,
) -> str:
    expected_fingerprint = production_demo_target_fingerprint(
        environment=environment,
        targets=targets,
        reset_mode=reset_mode,
        target_id=target_id,
        runtime_context=runtime_context,
    )
    if confirmation != PRODUCTION_DEMO_RESET_CONFIRMATION:
        raise RuntimeError(
            "production demo reset requires the exact --confirm-production-demo-reset value"
        )
    if runtime_stopped_confirmation != PRODUCTION_RUNTIME_STOPPED_CONFIRMATION:
        raise RuntimeError("production demo reset requires confirmation that ingress and workers are stopped")
    if target_fingerprint is None or not secrets.compare_digest(target_fingerprint, expected_fingerprint):
        raise RuntimeError("production demo reset target fingerprint does not match the resolved databases")
    return expected_fingerprint


def assert_safe_reset_targets(
    *,
    environment: str,
    targets: Iterable[tuple[str, str]],
    allowed_qa_hosts: Iterable[str] = (),
) -> None:
    normalized_environment = environment.strip().lower()
    if normalized_environment not in ALLOWED_RESET_ENVIRONMENTS:
        raise RuntimeError("destructive seed is allowed only when EDR_ENV is local or qa")

    qa_hosts = frozenset(host.strip().lower().rstrip(".") for host in allowed_qa_hosts)
    for label, dsn in targets:
        parsed = urlparse(dsn)
        host = (parsed.hostname or "").lower().rstrip(".")
        database = database_name(dsn)
        if not parsed.scheme or not host:
            raise RuntimeError(f"{label} DSN must include a scheme and host")
        is_local = host in LOCAL_RESET_HOSTS
        is_allowlisted_qa = normalized_environment == "qa" and host in qa_hosts
        if not (is_local or is_allowlisted_qa):
            raise RuntimeError(f"{label} host is not an allowlisted local/QA target: {host}")
        if database not in ALLOWED_RESET_DATABASES:
            raise RuntimeError(f"{label} database is not an allowlisted demo database: {database or '<missing>'}")
