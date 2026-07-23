"""Shared guardrails for destructive local and QA seed tools."""

from collections.abc import Iterable
from urllib.parse import unquote, urlparse

LOCAL_RESET_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "postgres", "clickhouse"})
ALLOWED_RESET_DATABASES = frozenset({"edr", "edr_qa", "test_edr"})
ALLOWED_RESET_ENVIRONMENTS = frozenset({"local", "qa"})


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
