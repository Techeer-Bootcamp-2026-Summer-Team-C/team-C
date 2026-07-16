from datetime import datetime
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
        event_type: str | None = None,
        process_name: str | None = None,
        file_path: str | None = None,
        domain: str | None = None,
        remote_ip: str | None = None,
        dns_query: str | None = None,
        dns_answer_ip: str | None = None,
        l7_protocol: str | None = None,
    ) -> list[JsonObject]:
        conditions = [
            "occurred_at >= {from:DateTime64(3)}",
            "occurred_at < {to:DateTime64(3)}",
            "is_delete = 0",
        ]
        parameters: dict[str, Any] = {"from": from_, "to": to}
        exact_filters = {
            "endpoint_id": (endpoint_id, "UInt64"),
            "event_type": (event_type, "String"),
            "remote_ip": (remote_ip, "String"),
        }
        for column, (value, type_name) in exact_filters.items():
            if value is not None:
                conditions.append(f"{column} = {{{column}:{type_name}}}")
                parameters[column] = value
        contains_filters = {
            "process_name": process_name,
            "file_path": file_path,
            "dns_query": dns_query,
        }
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
        if dns_answer_ip is not None:
            # dns_answers_json is a Nullable(String) column holding a JSON array of resolved
            # IPs (e.g. ["1.2.3.4","5.6.7.8"]); quote-wrap the value to avoid partial-IP matches.
            conditions.append("position(ifNull(dns_answers_json, ''), concat('\"', {dns_answer_ip:String}, '\"')) > 0")
            parameters["dns_answer_ip"] = dns_answer_ip
        if l7_protocol is not None:
            conditions.append("lowerUTF8(ifNull(l7_protocol, '')) = lowerUTF8({l7_protocol:String})")
            parameters["l7_protocol"] = l7_protocol
        result = self.client.query(
            f"SELECT {', '.join(EVENT_COLUMNS)} FROM edr_events FINAL WHERE {' AND '.join(conditions)}",
            parameters=parameters,
        )
        return [dict(zip(EVENT_COLUMNS, row, strict=True)) for row in result.result_rows]

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
            SELECT uniqExact(event_id), maxOrNull(ingested_at)
            FROM edr_events FINAL
            WHERE ingested_at >= {{from:DateTime64(3)}}
              AND ingested_at < {{to:DateTime64(3)}}
              AND is_delete = 0{endpoint_condition}
            """,
            parameters={"from": from_, "to": to, "endpoint_id": endpoint_id},
        )
        return int(result.result_rows[0][0]), result.result_rows[0][1]


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
    ) -> list[JsonObject]:
        conditions: list[str] = []
        parameters: dict[str, Any] = {}
        if from_ is not None:
            conditions.append("failed_at >= {from:DateTime64(3)}")
            parameters["from"] = from_
        if to is not None:
            conditions.append("failed_at < {to:DateTime64(3)}")
            parameters["to"] = to
        if status is not None:
            conditions.append("status = {status:String}")
            parameters["status"] = status
        if failure_stage is not None:
            conditions.append("failure_stage = {failure_stage:String}")
            parameters["failure_stage"] = failure_stage
        if retryable is not None:
            conditions.append("retryable = {retryable:Bool}")
            parameters["retryable"] = retryable
        if endpoint_id is not None:
            conditions.append("endpoint_id = {endpoint_id:UInt64}")
            parameters["endpoint_id"] = endpoint_id
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        result = self.client.query(
            f"SELECT {', '.join(FAILURE_COLUMNS)} FROM event_failures FINAL{where} "
            f"ORDER BY failed_at {sort_order.upper()}, failure_id {sort_order.upper()}",
            parameters=parameters,
        )
        return [dict(zip(FAILURE_COLUMNS, row, strict=True)) for row in result.result_rows]
