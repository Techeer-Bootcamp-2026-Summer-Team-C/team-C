from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID

from .models import EventIdentity, JsonObject


class ClickHouseClient(Protocol):
    def command(self, command: str, parameters: dict[str, Any] | None = None) -> Any: ...

    def query(self, query: str, parameters: dict[str, Any] | None = None) -> Any: ...

    def insert(self, table: str, data: list[list[Any]], column_names: list[str]) -> Any: ...


EVENT_COLUMNS = [
    "event_id",
    "batch_id",
    "endpoint_id",
    "agent_id",
    "hostname",
    "os_type",
    "ip_address",
    "event_type",
    "occurred_at",
    "ingested_at",
    "process_name",
    "process_path",
    "pid",
    "ppid",
    "command_line",
    "user_name",
    "file_path",
    "file_action",
    "file_hash_sha256",
    "remote_ip",
    "remote_domain",
    "remote_port",
    "protocol",
    "dns_query",
    "dns_record_type",
    "dns_response_code",
    "dns_answers_json",
    "l7_protocol",
    "http_method",
    "http_host",
    "url",
    "http_status_code",
    "http_user_agent",
    "tls_sni",
    "tls_version",
    "tls_certificate_subject",
    "tls_certificate_issuer",
    "tls_certificate_sha256",
    "raw_payload",
    "payload_sha256",
    "schema_version",
    "created_at",
    "updated_at",
    "is_delete",
]

FAILURE_COLUMNS = [
    "failure_id",
    "event_id",
    "endpoint_id",
    "source_topic",
    "source_partition",
    "source_offset",
    "consumer_name",
    "failure_stage",
    "failure_code",
    "error_message",
    "retryable",
    "retry_count",
    "payload_object_key",
    "payload_sha256",
    "payload_size_bytes",
    "status",
    "failed_at",
    "replay_count",
    "last_replayed_at",
    "reprocess_outcome",
    "resolved_at",
    "retention_expires_at",
    "created_at",
    "updated_at",
]

DASHBOARD_TOP_LIMIT = 10


def _failure_filters(
    *,
    from_: datetime | None = None,
    to: datetime | None = None,
    status: str | None = None,
    failure_stage: str | None = None,
    retryable: bool | None = None,
    endpoint_id: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    conditions: list[str] = []
    parameters: dict[str, Any] = {}
    if from_ is not None:
        conditions.append("failed_at >= {from:DateTime64(3)}")
        parameters["from"] = from_
    if to is not None:
        conditions.append("failed_at < {to:DateTime64(3)}")
        parameters["to"] = to
    exact_filters = {
        "status": (status, "String"),
        "failure_stage": (failure_stage, "String"),
        "retryable": (retryable, "Bool"),
        "endpoint_id": (endpoint_id, "UInt64"),
    }
    for column, (value, type_name) in exact_filters.items():
        if value is not None:
            conditions.append(f"{column} = {{{column}:{type_name}}}")
            parameters[column] = value
    return conditions, parameters


@dataclass(slots=True)
class DashboardEventAggregate:
    total_count: int = 0
    by_event_type: Counter[str] = field(default_factory=Counter)
    top_processes: Counter[str] = field(default_factory=Counter)
    top_remote_ips: Counter[str] = field(default_factory=Counter)
    top_domains: Counter[str] = field(default_factory=Counter)
    top_file_hashes: Counter[str] = field(default_factory=Counter)
    top_dns_queries: Counter[str] = field(default_factory=Counter)
    top_l7_protocols: Counter[str] = field(default_factory=Counter)
    time_series: Counter[datetime] = field(default_factory=Counter)


def _event_search_filters(
    *,
    from_: datetime,
    to: datetime,
    endpoint_id: int | None = None,
    endpoint_ids: list[int] | None = None,
    event_type: str | None = None,
    process_name: str | None = None,
    file_path: str | None = None,
    domain: str | None = None,
    related_domain: str | None = None,
    remote_ip: str | None = None,
    dns_query: str | None = None,
    dns_answer_ip: str | None = None,
    l7_protocol: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    conditions = [
        "occurred_at >= {from:DateTime64(3)}",
        "occurred_at < {to:DateTime64(3)}",
        "is_delete = 0",
    ]
    parameters: dict[str, Any] = {"from": from_, "to": to}
    if endpoint_ids:
        conditions.append("endpoint_id IN {endpoint_ids:Array(UInt64)}")
        parameters["endpoint_ids"] = endpoint_ids
    exact_filters = {
        "endpoint_id": (endpoint_id, "UInt64"),
        "event_type": (event_type, "String"),
        "remote_ip": (remote_ip, "String"),
    }
    for column, (value, type_name) in exact_filters.items():
        if value is not None:
            conditions.append(f"{column} = {{{column}:{type_name}}}")
            parameters[column] = value
    contains_filters = {"process_name": process_name, "file_path": file_path, "dns_query": dns_query}
    for column, value in contains_filters.items():
        if value is not None:
            conditions.append(f"positionCaseInsensitiveUTF8(ifNull({column}, ''), {{{column}:String}}) > 0")
            parameters[column] = value
    if domain is not None:
        conditions.append(
            "(positionCaseInsensitiveUTF8(ifNull(remote_domain, ''), {domain:String}) > 0 "
            "OR positionCaseInsensitiveUTF8(ifNull(http_host, ''), {domain:String}) > 0)"
        )
        parameters["domain"] = domain
    if related_domain is not None:
        related_columns = ("remote_domain", "http_host", "tls_sni", "dns_query")
        clauses = []
        for column in related_columns:
            clauses.append(f"lowerUTF8(ifNull({column}, '')) = lowerUTF8({{related_domain:String}})")
            clauses.append(
                f"endsWith(lowerUTF8(ifNull({column}, '')), lowerUTF8(concat('.', {{related_domain:String}})))"
            )
        conditions.append("(" + " OR ".join(clauses) + ")")
        parameters["related_domain"] = related_domain
    if dns_answer_ip is not None:
        conditions.append(
            "has(JSONExtract(ifNull(dns_answers_json, '[]'), 'Array(String)'), {dns_answer_ip:String})"
        )
        parameters["dns_answer_ip"] = dns_answer_ip
    if l7_protocol is not None:
        conditions.append("lowerUTF8(ifNull(l7_protocol, '')) = lowerUTF8({l7_protocol:String})")
        parameters["l7_protocol"] = l7_protocol
    return conditions, parameters


class EventRepository:
    def __init__(self, client: ClickHouseClient) -> None:
        self.client = client

    def insert(self, events: list[JsonObject]) -> None:
        if not events:
            return
        rows = [[event.get(column) for column in EVENT_COLUMNS] for event in events]
        self.client.insert("edr_events", rows, column_names=EVENT_COLUMNS)

    def identity(self, event_id: UUID) -> EventIdentity | None:
        result = self.client.query(
            """
            SELECT event_id, endpoint_id, agent_id, payload_sha256
            FROM edr_events FINAL
            WHERE event_id = {event_id:UUID} AND is_delete = 0
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            parameters={"event_id": str(event_id)},
        )
        if not result.result_rows:
            return None
        row = result.result_rows[0]
        payload_sha256 = row[3].decode("ascii") if isinstance(row[3], bytes) else str(row[3])
        return EventIdentity(UUID(str(row[0])), int(row[1]), str(row[2]), payload_sha256)

    def archive_count(self, *, endpoint_id: int, bucket_start_at: datetime) -> int:
        bucket_start_at = bucket_start_at.astimezone(UTC)
        result = self.client.query(
            """
            SELECT uniqExact(event_id)
            FROM edr_events FINAL
            WHERE endpoint_id = {endpoint_id:UInt64}
              AND occurred_at >= {from:DateTime64(3)}
              AND occurred_at < {to:DateTime64(3)}
              AND is_delete = 0
            """,
            parameters={
                "endpoint_id": endpoint_id,
                "from": bucket_start_at,
                "to": bucket_start_at + timedelta(days=1),
            },
        )
        return int(result.result_rows[0][0])

    def archive_row_batches(
        self,
        *,
        endpoint_id: int,
        bucket_start_at: datetime,
    ):
        bucket_start_at = bucket_start_at.astimezone(UTC)
        query = f"""
            SELECT {", ".join(EVENT_COLUMNS)}
            FROM edr_events FINAL
            WHERE endpoint_id = {{endpoint_id:UInt64}}
              AND occurred_at >= {{from:DateTime64(3)}}
              AND occurred_at < {{to:DateTime64(3)}}
              AND is_delete = 0
            ORDER BY occurred_at ASC, event_id ASC
        """
        parameters = {
            "endpoint_id": endpoint_id,
            "from": bucket_start_at,
            "to": bucket_start_at + timedelta(days=1),
        }
        with self.client.query_row_block_stream(query, parameters=parameters) as stream:
            for block in stream:
                yield [dict(zip(EVENT_COLUMNS, row, strict=True)) for row in block]

    def drop_partition(self, bucket_date: date) -> None:
        # ``bucket_date`` is already a typed ``date`` value, so formatting it here
        # avoids relying on query parameters in ClickHouse DDL statements.
        partition = bucket_date.isoformat()
        self.client.command(f"ALTER TABLE edr_events DROP PARTITION '{partition}'")

    def list_for_endpoint(
        self,
        *,
        endpoint_id: int,
        from_: datetime,
        to: datetime,
        page: int,
        size: int,
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> list[tuple[Any, ...]]:
        direction = "ASC" if sort_order == "asc" else "DESC"
        query = f"""
            SELECT {", ".join(EVENT_COLUMNS)}
            FROM edr_events FINAL
            WHERE endpoint_id = {{endpoint_id:UInt64}}
              AND occurred_at >= {{from:DateTime64(3)}}
              AND occurred_at < {{to:DateTime64(3)}}
              AND is_delete = 0
            ORDER BY occurred_at {direction}, event_id {direction}
            LIMIT {{limit:UInt64}} OFFSET {{offset:UInt64}}
        """
        result = self.client.query(
            query,
            parameters={
                "endpoint_id": endpoint_id,
                "from": from_,
                "to": to,
                "limit": size,
                "offset": (page - 1) * size,
            },
        )
        return list(result.result_rows)

    def count_for_endpoint(self, endpoint_id: int, from_: datetime, to: datetime) -> int:
        result = self.client.query(
            """
            SELECT uniqExact(event_id)
            FROM edr_events FINAL
            WHERE endpoint_id = {endpoint_id:UInt64}
              AND occurred_at >= {from:DateTime64(3)}
              AND occurred_at < {to:DateTime64(3)}
              AND is_delete = 0
            """,
            parameters={"endpoint_id": endpoint_id, "from": from_, "to": to},
        )
        return int(result.result_rows[0][0])

    def search(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
        endpoint_ids: list[int] | None = None,
        event_type: str | None = None,
        process_name: str | None = None,
        file_path: str | None = None,
        domain: str | None = None,
        related_domain: str | None = None,
        remote_ip: str | None = None,
        dns_query: str | None = None,
        dns_answer_ip: str | None = None,
        l7_protocol: str | None = None,
        sort_order: Literal["asc", "desc"] | None = None,
        limit: int | None = None,
        offset: int = 0,
        columns: list[str] | None = None,
    ) -> list[JsonObject]:
        conditions, parameters = _event_search_filters(
            from_=from_,
            to=to,
            endpoint_id=endpoint_id,
            endpoint_ids=endpoint_ids,
            event_type=event_type,
            process_name=process_name,
            file_path=file_path,
            domain=domain,
            related_domain=related_domain,
            remote_ip=remote_ip,
            dns_query=dns_query,
            dns_answer_ip=dns_answer_ip,
            l7_protocol=l7_protocol,
        )
        suffix = ""
        if sort_order is not None:
            direction = sort_order.upper()
            suffix += f" ORDER BY occurred_at {direction}, event_id {direction}"
        if limit is not None:
            suffix += " LIMIT {limit:UInt64} OFFSET {offset:UInt64}"
            parameters.update({"limit": limit, "offset": offset})
        selected_columns = columns or EVENT_COLUMNS
        if not selected_columns or any(column not in EVENT_COLUMNS for column in selected_columns):
            raise ValueError("event search projection contains an unknown column")
        result = self.client.query(
            f"SELECT {', '.join(selected_columns)} FROM edr_events FINAL WHERE {' AND '.join(conditions)}{suffix}",
            parameters=parameters,
        )
        return [dict(zip(selected_columns, row, strict=True)) for row in result.result_rows]

    def count_search(self, **filters: Any) -> int:
        conditions, parameters = _event_search_filters(**filters)
        result = self.client.query(
            f"SELECT uniqExact(event_id) FROM edr_events FINAL WHERE {' AND '.join(conditions)}",
            parameters=parameters,
        )
        return int(result.result_rows[0][0])

    def detail(self, *, event_id: UUID, endpoint_id: int, occurred_at: datetime) -> JsonObject | None:
        result = self.client.query(
            f"""
            SELECT {", ".join(EVENT_COLUMNS)} FROM edr_events FINAL
            WHERE event_id = {{event_id:UUID}} AND endpoint_id = {{endpoint_id:UInt64}}
              AND toDate(occurred_at) = toDate({{occurred_at:DateTime64(3)}}) AND is_delete = 0
            ORDER BY updated_at DESC LIMIT 1
            """,
            parameters={"event_id": str(event_id), "endpoint_id": endpoint_id, "occurred_at": occurred_at},
        )
        if not result.result_rows:
            return None
        return dict(zip(EVENT_COLUMNS, result.result_rows[0], strict=True))

    def details(self, identities: list[tuple[UUID, int, datetime]]) -> list[JsonObject]:
        if not identities:
            return []
        clauses: list[str] = []
        parameters: dict[str, Any] = {}
        for index, (event_id, endpoint_id, occurred_at) in enumerate(dict.fromkeys(identities)):
            bucket_start = occurred_at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            clauses.append(
                f"(event_id = {{event_id_{index}:UUID}} "
                f"AND endpoint_id = {{endpoint_id_{index}:UInt64}} "
                f"AND occurred_at >= {{from_{index}:DateTime64(3)}} "
                f"AND occurred_at < {{to_{index}:DateTime64(3)}})"
            )
            parameters.update(
                {
                    f"event_id_{index}": str(event_id),
                    f"endpoint_id_{index}": endpoint_id,
                    f"from_{index}": bucket_start,
                    f"to_{index}": bucket_start + timedelta(days=1),
                }
            )
        result = self.client.query(
            f"""
            SELECT {", ".join(EVENT_COLUMNS)} FROM edr_events FINAL
            WHERE is_delete = 0 AND ({" OR ".join(clauses)})
            ORDER BY updated_at DESC
            """,
            parameters=parameters,
        )
        rows: dict[str, JsonObject] = {}
        for result_row in result.result_rows:
            row = dict(zip(EVENT_COLUMNS, result_row, strict=True))
            rows.setdefault(str(row["event_id"]), row)
        return list(rows.values())

    def ingest_summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
    ) -> tuple[int, datetime | None]:
        endpoint_condition = (
            " AND endpoint_id = {endpoint_id:UInt64}" if endpoint_id is not None else ""
        )
        result = self.client.query(
            f"""
            SELECT count(), maxOrNull(ingested_at)
            FROM edr_events FINAL
            WHERE ingested_at >= {{from:DateTime64(3)}}
              AND ingested_at < {{to:DateTime64(3)}}
              AND is_delete = 0{endpoint_condition}
            """,
            parameters={"from": from_, "to": to, "endpoint_id": endpoint_id},
        )
        return int(result.result_rows[0][0]), result.result_rows[0][1]

    def latest_ingested_at(self, *, endpoint_id: int | None = None) -> datetime | None:
        endpoint_condition = (
            " AND endpoint_id = {endpoint_id:UInt64}" if endpoint_id is not None else ""
        )
        result = self.client.query(
            f"""
            SELECT maxOrNull(ingested_at)
            FROM edr_events FINAL
            WHERE is_delete = 0{endpoint_condition}
            """,
            parameters={"endpoint_id": endpoint_id},
        )
        return result.result_rows[0][0]

    def dashboard_summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        interval_seconds: int,
        endpoint_id: int | None = None,
    ) -> DashboardEventAggregate:
        if interval_seconds not in {60, 300, 3600, 86400}:
            raise ValueError("unsupported dashboard interval")

        conditions = [
            "occurred_at >= {from:DateTime64(3)}",
            "occurred_at < {to:DateTime64(3)}",
            "is_delete = 0",
        ]
        parameters: dict[str, Any] = {"from": from_, "to": to}
        if endpoint_id is not None:
            conditions.append("endpoint_id = {endpoint_id:UInt64}")
            parameters["endpoint_id"] = endpoint_id
        where = " AND ".join(conditions)

        total = self.client.query(
            f"SELECT count() FROM edr_events FINAL WHERE {where}",
            parameters=parameters,
        )
        aggregate = DashboardEventAggregate(total_count=int(total.result_rows[0][0]))

        by_event_type = self.client.query(
            f"""
            SELECT event_type, count()
            FROM edr_events FINAL
            WHERE {where}
            GROUP BY event_type
            """,
            parameters=parameters,
        )
        aggregate.by_event_type.update(
            {str(value): int(count) for value, count in by_event_type.result_rows}
        )

        time_series = self.client.query(
            f"""
            SELECT
                toStartOfInterval(occurred_at, INTERVAL {interval_seconds} SECOND, 'UTC') AS bucket_start_at,
                count()
            FROM edr_events FINAL
            WHERE {where}
            GROUP BY bucket_start_at
            ORDER BY bucket_start_at
            """,
            parameters=parameters,
        )
        aggregate.time_series.update(
            {
                _utc_datetime(bucket_start_at): int(count)
                for bucket_start_at, count in time_series.result_rows
            }
        )

        top_dimensions = (
            ("top_processes", "process_name"),
            ("top_remote_ips", "remote_ip"),
            (
                "top_domains",
                "coalesce(nullIf(remote_domain, ''), nullIf(http_host, ''))",
            ),
            ("top_file_hashes", "file_hash_sha256"),
            ("top_dns_queries", "dns_query"),
            ("top_l7_protocols", "l7_protocol"),
        )
        for target, expression in top_dimensions:
            result = self.client.query(
                f"""
                SELECT {expression} AS value, count() AS event_count
                FROM edr_events FINAL
                WHERE {where}
                  AND isNotNull({expression})
                  AND {expression} != ''
                GROUP BY value
                ORDER BY event_count DESC, value ASC
                LIMIT {DASHBOARD_TOP_LIMIT}
                """,
                parameters=parameters,
            )
            getattr(aggregate, target).update(
                {str(value): int(count) for value, count in result.result_rows}
            )

        return aggregate


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class FailureRepository:
    def __init__(self, client: ClickHouseClient) -> None:
        self.client = client

    def insert(self, failures: list[JsonObject]) -> None:
        if not failures:
            return
        rows = [[failure.get(column) for column in FAILURE_COLUMNS] for failure in failures]
        self.client.insert("event_failures", rows, column_names=FAILURE_COLUMNS)

    def latest_status(self, failure_id: UUID) -> str | None:
        result = self.client.query(
            """
            SELECT status
            FROM event_failures FINAL
            WHERE failure_id = {failure_id:UUID}
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            parameters={"failure_id": str(failure_id)},
        )
        if not result.result_rows:
            return None
        return str(result.result_rows[0][0])

    def latest(self, failure_id: UUID) -> JsonObject | None:
        result = self.client.query(
            f"""
            SELECT {", ".join(FAILURE_COLUMNS)}
            FROM event_failures FINAL
            WHERE failure_id = {{failure_id:UUID}}
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            parameters={"failure_id": str(failure_id)},
        )
        if not result.result_rows:
            return None
        return dict(zip(FAILURE_COLUMNS, result.result_rows[0], strict=True))

    def append_replay_result(
        self,
        failure: JsonObject,
        *,
        status: str,
        outcome: str,
        replayed_at: datetime,
    ) -> None:
        updated = dict(failure)
        updated["status"] = status
        updated["replay_count"] = int(failure["replay_count"]) + 1
        updated["last_replayed_at"] = replayed_at
        updated["reprocess_outcome"] = outcome
        updated["resolved_at"] = replayed_at if status == "REPROCESSED" else None
        updated["updated_at"] = replayed_at
        self.insert([updated])

    def current_rows(
        self,
        *,
        from_: datetime | None = None,
        to: datetime | None = None,
        status: str | None = None,
        failure_stage: str | None = None,
        retryable: bool | None = None,
        endpoint_id: int | None = None,
        sort_order: Literal["asc", "desc"] = "desc",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonObject]:
        conditions, parameters = _failure_filters(
            from_=from_,
            to=to,
            status=status,
            failure_stage=failure_stage,
            retryable=retryable,
            endpoint_id=endpoint_id,
        )
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        pagination = ""
        if limit is not None:
            pagination = " LIMIT {limit:UInt64} OFFSET {offset:UInt64}"
            parameters.update({"limit": limit, "offset": offset})
        result = self.client.query(
            f"SELECT {', '.join(FAILURE_COLUMNS)} FROM event_failures FINAL{where} "
            f"ORDER BY failed_at {sort_order.upper()}, failure_id {sort_order.upper()}{pagination}",
            parameters=parameters,
        )
        return [dict(zip(FAILURE_COLUMNS, row, strict=True)) for row in result.result_rows]

    def count_current(self, **filters: Any) -> int:
        conditions, parameters = _failure_filters(**filters)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        result = self.client.query(
            f"SELECT uniqExact(failure_id) FROM event_failures FINAL{where}",
            parameters=parameters,
        )
        return int(result.result_rows[0][0])

    def summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
    ) -> dict[str, Any]:
        conditions, parameters = _failure_filters(from_=from_, to=to, endpoint_id=endpoint_id)
        where = " AND ".join(conditions)

        def grouped(column: str) -> dict[str | None, int]:
            result = self.client.query(
                f"""
                SELECT {column}, count()
                FROM event_failures FINAL
                WHERE {where}
                GROUP BY {column}
                """,
                parameters=parameters,
            )
            return {
                (None if value is None else str(value)): int(count)
                for value, count in result.result_rows
            }

        total = self.client.query(
            f"""
            SELECT uniqExact(failure_id)
            FROM event_failures FINAL
            WHERE {where}
            """,
            parameters=parameters,
        ).result_rows[0]
        oldest_failed = self.client.query(
            f"""
            SELECT minOrNull(failed_at)
            FROM event_failures FINAL
            WHERE {where} AND status = 'FAILED'
            """,
            parameters=parameters,
        ).result_rows[0][0]
        return {
            "total": int(total[0]),
            "oldest_failed_at": oldest_failed,
            "by_stage": grouped("failure_stage"),
            "by_code": grouped("failure_code"),
            "by_status": grouped("status"),
        }
