import json
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

import pyarrow.fs as pafs
import pyarrow.parquet as pq

from .contracts.events import EventDetailDto, EventDto
from .contracts.requests import EventListQuery
from .errors import ApplicationError
from .storage.clickhouse import DashboardEventAggregate, EventRepository
from .storage.postgres import IngestMetadataRepository

UNREADY_STATUSES = {"ARCHIVED", "RESTORE_REQUESTED", "RESTORE_FAILED", "EXPIRED"}


class RestoredReaderPort(Protocol):
    def read_rows(self, object_key: str) -> list[dict[str, Any]]: ...


class RestoredEventReader:
    def __init__(
        self,
        *,
        region: str | None,
        endpoint_url: str | None,
        access_key: str | None,
        secret_key: str | None,
        bucket: str,
    ) -> None:
        self.bucket = bucket
        options: dict[str, str] = {}
        if region is not None:
            options["region"] = region
        if endpoint_url is not None:
            parsed = urlparse(endpoint_url)
            options["endpoint_override"] = parsed.netloc
            options["scheme"] = parsed.scheme
        if access_key is not None and secret_key is not None:
            options["access_key"] = access_key
            options["secret_key"] = secret_key
        self.filesystem = pafs.S3FileSystem(**options)

    def read_rows(self, object_key: str) -> list[dict[str, Any]]:
        table = pq.read_table(f"{self.bucket}/{object_key}", filesystem=self.filesystem)
        return [dict(row) for row in table.to_pylist()]


class EventService:
    def __init__(
        self,
        *,
        events: EventRepository,
        metadata: IngestMetadataRepository,
        restored: RestoredReaderPort,
    ) -> None:
        self.events = events
        self.metadata = metadata
        self.restored = restored

    def list_rows(self, query: EventListQuery, *, from_: datetime, to: datetime) -> tuple[list[EventDto], int]:
        metadata_rows = self.metadata.overlapping_all(
            from_=from_,
            to=to,
            endpoint_ids=[query.endpoint_id] if query.endpoint_id is not None else None,
        )
        hot_keys = {
            (int(row["endpoint_id"]), _utc(row["bucket_start_at"]))
            for row in metadata_rows
            if row["storage_backend"] == "CLICKHOUSE" and row["storage_status"] == "HOT"
        }
        unready = [
            row
            for row in metadata_rows
            if row["storage_backend"] == "S3"
            and row["storage_status"] in UNREADY_STATUSES
            and (int(row["endpoint_id"]), _utc(row["bucket_start_at"])) not in hot_keys
        ]
        if unready:
            raise _archive_not_ready(unready)

        hot = self.events.search(
            from_=from_,
            to=to,
            endpoint_id=query.endpoint_id,
            event_type=query.event_type.value if query.event_type else None,
            process_name=query.process_name,
            file_path=query.file_path,
            domain=query.domain,
            remote_ip=query.remote_ip,
            dns_query=query.dns_query,
            l7_protocol=query.l7_protocol,
        )
        merged: dict[str, dict[str, Any]] = {str(row["event_id"]): row for row in hot}
        restored_rows = [
            row
            for row in metadata_rows
            if row["storage_backend"] == "S3"
            and row["storage_status"] == "RESTORED"
            and (int(row["endpoint_id"]), _utc(row["bucket_start_at"])) not in hot_keys
        ]
        for bucket in restored_rows:
            for row in self.restored.read_rows(str(bucket["storage_path"])):
                if self._matches(row, query, from_, to):
                    merged.setdefault(str(row["event_id"]), row)
        rows = list(merged.values())
        reverse = query.sort_order == "desc"
        rows.sort(key=lambda row: (_utc(row["occurred_at"]), str(row["event_id"])), reverse=reverse)
        total = len(rows)
        start = (query.page - 1) * query.size
        return [_event_dto(row) for row in rows[start : start + query.size]], total

    def dashboard_summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        interval_seconds: int,
        endpoint_id: int | None = None,
    ) -> DashboardEventAggregate:
        metadata_rows = self.metadata.overlapping_all(
            from_=from_,
            to=to,
            endpoint_ids=[endpoint_id] if endpoint_id is not None else None,
        )
        hot_keys = {
            (int(row["endpoint_id"]), _utc(row["bucket_start_at"]))
            for row in metadata_rows
            if row["storage_backend"] == "CLICKHOUSE" and row["storage_status"] == "HOT"
        }
        unready = [
            row
            for row in metadata_rows
            if row["storage_backend"] == "S3"
            and row["storage_status"] in UNREADY_STATUSES
            and (int(row["endpoint_id"]), _utc(row["bucket_start_at"])) not in hot_keys
        ]
        if unready:
            raise _archive_not_ready(unready)

        aggregate = self.events.dashboard_summary(
            from_=from_,
            to=to,
            interval_seconds=interval_seconds,
            endpoint_id=endpoint_id,
        )
        restored_rows = [
            row
            for row in metadata_rows
            if row["storage_backend"] == "S3"
            and row["storage_status"] == "RESTORED"
            and (int(row["endpoint_id"]), _utc(row["bucket_start_at"])) not in hot_keys
        ]
        seen_restored: set[str] = set()
        for bucket in restored_rows:
            for row in self.restored.read_rows(str(bucket["storage_path"])):
                occurred_at = _utc(row["occurred_at"])
                if not from_ <= occurred_at < to:
                    continue
                if endpoint_id is not None and int(row["endpoint_id"]) != endpoint_id:
                    continue
                event_id = str(row["event_id"])
                if event_id in seen_restored:
                    continue
                seen_restored.add(event_id)
                _add_dashboard_event(aggregate, row, occurred_at, interval_seconds)
        return aggregate

    def detail(self, *, event_id: UUID, endpoint_id: int, occurred_at: datetime) -> EventDetailDto | None:
        bucket_start = occurred_at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        metadata_rows = self.metadata.overlapping_all(
            from_=bucket_start,
            to=bucket_start + timedelta(days=1),
            endpoint_ids=[endpoint_id],
        )
        hot = any(row["storage_backend"] == "CLICKHOUSE" and row["storage_status"] == "HOT" for row in metadata_rows)
        if hot or not metadata_rows:
            row = self.events.detail(event_id=event_id, endpoint_id=endpoint_id, occurred_at=occurred_at)
            return _event_detail_dto(row) if row is not None else None
        restored = next(
            (row for row in metadata_rows if row["storage_backend"] == "S3" and row["storage_status"] == "RESTORED"),
            None,
        )
        if restored is not None:
            for row in self.restored.read_rows(str(restored["storage_path"])):
                if str(row["event_id"]) == str(event_id) and int(row["endpoint_id"]) == endpoint_id:
                    return _event_detail_dto(row)
            return None
        unready = [row for row in metadata_rows if row["storage_status"] in UNREADY_STATUSES]
        if unready:
            raise _archive_not_ready(unready)
        return None

    @staticmethod
    def _matches(row: dict[str, Any], query: EventListQuery, from_: datetime, to: datetime) -> bool:
        occurred_at = _utc(row["occurred_at"])
        if not from_ <= occurred_at < to:
            return False
        if query.endpoint_id is not None and int(row["endpoint_id"]) != query.endpoint_id:
            return False
        if query.event_type is not None and str(row["event_type"]) != query.event_type.value:
            return False
        contains = (
            ("process_name", query.process_name),
            ("file_path", query.file_path),
            ("dns_query", query.dns_query),
        )
        if any(
            value is not None and value.lower() not in str(row.get(field) or "").lower() for field, value in contains
        ):
            return False
        if query.domain is not None:
            domains = (str(row.get("remote_domain") or ""), str(row.get("http_host") or ""))
            if not any(query.domain.lower() in value.lower() for value in domains):
                return False
        if query.remote_ip is not None and str(row.get("remote_ip")) != query.remote_ip:
            return False
        return query.l7_protocol is None or str(row.get("l7_protocol") or "").lower() == query.l7_protocol.lower()


def _event_dto(row: dict[str, Any]) -> EventDto:
    values = dict(row)
    values["event_id"] = str(values.get("event_id"))
    values["batch_id"] = str(values.get("batch_id"))
    values["occurred_at"] = _utc(values["occurred_at"])
    values["ingested_at"] = _utc(values["ingested_at"])
    answers = values.pop("dns_answers_json", None)
    values["dns_answers"] = _json_list(answers)
    return EventDto.model_validate({field: values.get(field) for field in EventDto.model_fields})


def _event_detail_dto(row: dict[str, Any]) -> EventDetailDto:
    base = _event_dto(row).model_dump()
    raw = row.get("raw_payload")
    base.update(
        raw_payload=json.loads(raw) if isinstance(raw, str) else dict(raw or {}),
        payload_sha256=_fixed_string(row.get("payload_sha256", "")),
        schema_version=int(row.get("schema_version", 0)),
    )
    return EventDetailDto.model_validate(base)


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parsed = json.loads(value)
        return list(parsed) if isinstance(parsed, list) else []
    return list(value) if isinstance(value, list) else []


def _fixed_string(value: Any) -> str:
    return value.decode("ascii") if isinstance(value, bytes) else str(value)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _add_dashboard_event(
    aggregate: DashboardEventAggregate,
    row: dict[str, Any],
    occurred_at: datetime,
    interval_seconds: int,
) -> None:
    aggregate.total_count += 1
    aggregate.by_event_type[str(row["event_type"])] += 1
    values = (
        (aggregate.top_processes, row.get("process_name")),
        (aggregate.top_remote_ips, row.get("remote_ip")),
        (aggregate.top_domains, row.get("remote_domain") or row.get("http_host")),
        (aggregate.top_file_hashes, row.get("file_hash_sha256")),
        (aggregate.top_dns_queries, row.get("dns_query")),
        (aggregate.top_l7_protocols, row.get("l7_protocol")),
    )
    for counter, value in values:
        if value is not None and value != "":
            counter[str(value)] += 1
    epoch = int(occurred_at.timestamp())
    bucket_start_at = datetime.fromtimestamp(
        (epoch // interval_seconds) * interval_seconds,
        tz=UTC,
    )
    aggregate.time_series[bucket_start_at] += 1


def _archive_not_ready(rows: list[dict[str, Any]]) -> ApplicationError:
    details = [
        {
            "field": None,
            "message": "Archive bucket is not ready.",
            "context": {
                "endpointId": int(row["endpoint_id"]),
                "bucketStartAt": _utc(row["bucket_start_at"]).isoformat().replace("+00:00", "Z"),
                "storageStatus": str(row["storage_status"]),
            },
        }
        for row in rows
    ]
    return ApplicationError(409, "ARCHIVE_NOT_READY", "One or more archive buckets are not ready.", details=details)
