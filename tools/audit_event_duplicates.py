import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import clickhouse_connect

from backend.settings import get_settings


class QueryResult(Protocol):
    result_rows: list[tuple[Any, ...]]


class QueryClient(Protocol):
    def query(self, query: str, parameters: dict[str, Any] | None = None) -> QueryResult: ...


@dataclass(frozen=True, slots=True)
class EventDuplicateFinding:
    event_id: str
    physical_row_count: int
    identity_count: int
    first_occurred_at: str
    last_occurred_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "eventId": self.event_id,
            "physicalRowCount": self.physical_row_count,
            "identityCount": self.identity_count,
            "firstOccurredAt": self.first_occurred_at,
            "lastOccurredAt": self.last_occurred_at,
        }


@dataclass(frozen=True, slots=True)
class EventDuplicateAudit:
    duplicate_event_ids: int
    extra_physical_rows: int
    conflicting_event_ids: int
    findings: tuple[EventDuplicateFinding, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "duplicateEventIds": self.duplicate_event_ids,
            "extraPhysicalRows": self.extra_physical_rows,
            "conflictingEventIds": self.conflicting_event_ids,
            "truncated": self.duplicate_event_ids > len(self.findings),
            "findings": [finding.as_dict() for finding in self.findings],
        }


def audit_event_duplicates(client: QueryClient, *, limit: int = 100) -> EventDuplicateAudit:
    if not 1 <= limit <= 10_000:
        raise ValueError("duplicate audit limit must be between 1 and 10000")
    summary_row = client.query(
        """
        SELECT
            count() AS duplicate_event_ids,
            ifNull(sum(physical_row_count - 1), 0) AS extra_physical_rows,
            countIf(identity_count > 1) AS conflicting_event_ids
        FROM (
            SELECT
                event_id,
                count() AS physical_row_count,
                uniqExact(endpoint_id, agent_id, payload_sha256) AS identity_count
            FROM edr_events
            GROUP BY event_id
            HAVING physical_row_count > 1
        )
        SETTINGS max_execution_time = 60, max_threads = 2
        """
    ).result_rows[0]
    duplicate_event_ids = int(summary_row[0])
    if duplicate_event_ids == 0:
        return EventDuplicateAudit(0, 0, 0, ())
    rows = client.query(
        """
        SELECT
            event_id,
            count() AS physical_row_count,
            uniqExact(endpoint_id, agent_id, payload_sha256) AS identity_count,
            min(occurred_at) AS first_occurred_at,
            max(occurred_at) AS last_occurred_at
        FROM edr_events
        GROUP BY event_id
        HAVING physical_row_count > 1
        ORDER BY identity_count DESC, physical_row_count DESC, event_id ASC
        LIMIT {limit:UInt32}
        SETTINGS max_execution_time = 60, max_threads = 2
        """,
        parameters={"limit": limit},
    ).result_rows
    findings = tuple(
        EventDuplicateFinding(
            event_id=str(row[0]),
            physical_row_count=int(row[1]),
            identity_count=int(row[2]),
            first_occurred_at=_timestamp(row[3]),
            last_occurred_at=_timestamp(row[4]),
        )
        for row in rows
    )
    return EventDuplicateAudit(
        duplicate_event_ids=duplicate_event_ids,
        extra_physical_rows=int(summary_row[1]),
        conflicting_event_ids=int(summary_row[2]),
        findings=findings,
    )


def _timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit physical and conflicting event_id duplicates in ClickHouse.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum duplicate event IDs to include (1-10000).")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return exit code 2 when duplicate event IDs are found.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = None
    try:
        settings = get_settings()
        client = clickhouse_connect.get_client(
            dsn=settings.clickhouse_dsn.get_secret_value(),
            autogenerate_session_id=False,
            connect_timeout=5,
            send_receive_timeout=60,
        )
        audit = audit_event_duplicates(client, limit=args.limit)
    except Exception as error:
        print(f"event duplicate audit failed: {error}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
    print(json.dumps(audit.as_dict(), ensure_ascii=False, indent=2))
    if args.fail_on_findings and audit.duplicate_event_ids > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
