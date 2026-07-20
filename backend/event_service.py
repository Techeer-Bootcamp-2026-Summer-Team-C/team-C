import hashlib
import heapq
import json
import sqlite3
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

import pyarrow.dataset as pads
import pyarrow.fs as pafs

from .contracts.events import EventDetailDto, EventDto
from .contracts.requests import EventListQuery
from .errors import ApplicationError, ServiceUnavailableError
from .storage.clickhouse import DashboardEventAggregate, EventRepository
from .storage.postgres import IngestMetadataRepository

UNREADY_STATUSES = {"ARCHIVED", "RESTORE_REQUESTED", "RESTORE_FAILED", "EXPIRED"}
PARQUET_BATCH_SIZE = 1_024
MAX_RESTORED_PAGE_WINDOW = 10_000
MAX_RESTORED_DASHBOARD_EVENTS = 1_000_000
EVENT_LIST_COLUMNS = [field for field in EventDto.model_fields if field != "dns_answers"] + ["dns_answers_json"]
EVENT_DETAIL_COLUMNS = EVENT_LIST_COLUMNS + ["raw_payload", "payload_sha256", "schema_version"]
EVENT_DASHBOARD_COLUMNS = [
    "event_id",
    "endpoint_id",
    "event_type",
    "occurred_at",
    "process_name",
    "remote_ip",
    "remote_domain",
    "http_host",
    "file_hash_sha256",
    "dns_query",
    "l7_protocol",
]


class RestoredReaderPort(Protocol):
    def read_rows(self, object_key: str, **filters: Any) -> Iterator[dict[str, Any]]: ...


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
        options: dict[str, Any] = {"connect_timeout": 5, "request_timeout": 10}
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

    def read_rows(
        self,
        object_key: str,
        *,
        columns: list[str] | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        endpoint_id: int | None = None,
        event_type: str | None = None,
        remote_ip: str | None = None,
        event_id: str | None = None,
        event_ids: list[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        try:
            expression = None
            exact_filters = {
                "endpoint_id": endpoint_id,
                "event_type": event_type,
                "remote_ip": remote_ip,
                "event_id": event_id,
            }
            predicates = []
            if from_ is not None:
                predicates.append(pads.field("occurred_at") >= from_)
            if to is not None:
                predicates.append(pads.field("occurred_at") < to)
            predicates.extend(pads.field(field) == value for field, value in exact_filters.items() if value is not None)
            if event_ids:
                predicates.append(pads.field("event_id").isin(event_ids))
            for predicate in predicates:
                expression = predicate if expression is None else expression & predicate
            dataset = pads.dataset(
                f"{self.bucket}/{object_key}",
                filesystem=self.filesystem,
                format="parquet",
            )
            scanner = dataset.scanner(
                columns=columns,
                filter=expression,
                batch_size=PARQUET_BATCH_SIZE,
                use_threads=False,
            )
            for batch in scanner.to_batches():
                yield from (dict(row) for row in batch.to_pylist())
        except Exception as error:
            raise ServiceUnavailableError("Restored event archive is temporarily unavailable.") from error


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
        hot_keys = _ensure_archive_rows_ready(metadata_rows)

        filters = dict(
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
        restored_rows = [
            row
            for row in metadata_rows
            if row["storage_backend"] == "S3"
            and row["storage_status"] == "RESTORED"
            and (int(row["endpoint_id"]), _utc(row["bucket_start_at"])) not in hot_keys
        ]
        offset = (query.page - 1) * query.size
        if not restored_rows:
            rows = self.events.search(
                **filters,
                sort_order=query.sort_order,
                limit=query.size,
                offset=offset,
            )
            return [_event_dto(row) for row in rows], self.events.count_search(**filters)

        window = offset + query.size
        if window > MAX_RESTORED_PAGE_WINDOW:
            raise ApplicationError(
                400,
                "VALIDATION_ERROR",
                f"Restored archive pagination cannot exceed {MAX_RESTORED_PAGE_WINDOW} rows.",
            )
        hot = self.events.search(**filters, sort_order=query.sort_order, limit=window)
        restored, restored_total = self._restored_page(
            restored_rows,
            query=query,
            from_=from_,
            to=to,
            limit=window,
        )
        rows = hot + restored
        reverse = query.sort_order == "desc"
        rows.sort(key=lambda row: (_utc(row["occurred_at"]), str(row["event_id"])), reverse=reverse)
        total = self.events.count_search(**filters) + restored_total
        return [_event_dto(row) for row in rows[offset:window]], total

    def _restored_page(
        self,
        buckets: list[dict[str, Any]],
        *,
        query: EventListQuery,
        from_: datetime,
        to: datetime,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        heap: list[tuple[int, int, dict[str, Any]]] = []
        total = 0
        ordered_buckets = sorted(
            buckets,
            key=lambda bucket: _utc(bucket["bucket_start_at"]),
            reverse=query.sort_order == "desc",
        )
        for bucket in ordered_buckets:
            metadata_count = _exact_bucket_count(bucket, query=query, from_=from_, to=to)
            if metadata_count is not None:
                total += metadata_count
                if len(heap) >= limit and not _bucket_can_improve(bucket, heap[0][0], query.sort_order):
                    continue
            for row in self.restored.read_rows(
                str(bucket["storage_path"]),
                columns=EVENT_LIST_COLUMNS,
                from_=from_,
                to=to,
                endpoint_id=query.endpoint_id,
                event_type=query.event_type.value if query.event_type else None,
                remote_ip=query.remote_ip,
            ):
                if not self._matches(row, query, from_, to):
                    continue
                if metadata_count is None:
                    total += 1
                occurred_key, event_key = _event_order_key(row)
                entry = (
                    (occurred_key if query.sort_order == "desc" else -occurred_key),
                    (event_key if query.sort_order == "desc" else -event_key),
                    row,
                )
                if len(heap) < limit:
                    heapq.heappush(heap, entry)
                elif entry[:2] > heap[0][:2]:
                    heapq.heapreplace(heap, entry)
        return [entry[2] for entry in heap], total

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
        hot_keys = _ensure_archive_rows_ready(metadata_rows)

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
        estimated_restored_count = sum(int(row.get("event_count") or 0) for row in restored_rows)
        if estimated_restored_count > MAX_RESTORED_DASHBOARD_EVENTS:
            raise ApplicationError(
                400,
                "VALIDATION_ERROR",
                "Restored archive dashboard range is too large; narrow the time range or Endpoint filter.",
            )
        with _RestoredDashboardAccumulator(interval_seconds) as restored_aggregate:
            for bucket in restored_rows:
                for row in self.restored.read_rows(
                    str(bucket["storage_path"]),
                    columns=EVENT_DASHBOARD_COLUMNS,
                    from_=from_,
                    to=to,
                    endpoint_id=endpoint_id,
                ):
                    occurred_at = _utc(row["occurred_at"])
                    if not from_ <= occurred_at < to:
                        continue
                    if endpoint_id is not None and int(row["endpoint_id"]) != endpoint_id:
                        continue
                    restored_aggregate.add(row, occurred_at)
            _merge_dashboard_aggregate(aggregate, restored_aggregate.result())
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
            for row in self.restored.read_rows(
                str(restored["storage_path"]),
                columns=EVENT_DETAIL_COLUMNS,
                from_=bucket_start,
                to=bucket_start + timedelta(days=1),
                endpoint_id=endpoint_id,
                event_id=str(event_id),
            ):
                if str(row["event_id"]) == str(event_id) and int(row["endpoint_id"]) == endpoint_id:
                    return _event_detail_dto(row)
            return None
        unready = [row for row in metadata_rows if row["storage_status"] in UNREADY_STATUSES]
        if unready:
            raise _archive_not_ready(unready)
        return None

    def details_bulk(
        self,
        identities: list[tuple[UUID, int, datetime]],
    ) -> tuple[dict[str, EventDetailDto], set[str]]:
        if not identities:
            return {}, set()
        normalized = [
            (event_id, endpoint_id, _utc(occurred_at))
            for event_id, endpoint_id, occurred_at in identities
        ]
        bucket_keys = {
            (endpoint_id, occurred_at.replace(hour=0, minute=0, second=0, microsecond=0))
            for _event_id, endpoint_id, occurred_at in normalized
        }
        from_ = min(bucket_start for _endpoint_id, bucket_start in bucket_keys)
        to = max(bucket_start for _endpoint_id, bucket_start in bucket_keys) + timedelta(days=1)
        metadata_rows = self.metadata.overlapping_all(
            from_=from_,
            to=to,
            endpoint_ids=sorted({endpoint_id for endpoint_id, _bucket_start in bucket_keys}),
        )
        rows_by_key: dict[tuple[int, datetime], list[dict[str, Any]]] = {}
        for row in metadata_rows:
            key = (int(row["endpoint_id"]), _utc(row["bucket_start_at"]))
            rows_by_key.setdefault(key, []).append(row)

        hot_identities: list[tuple[UUID, int, datetime]] = []
        restored_groups: dict[tuple[int, datetime, str], list[str]] = {}
        unavailable: set[str] = set()
        for event_id, endpoint_id, occurred_at in normalized:
            rendered = str(event_id)
            bucket_start = occurred_at.replace(hour=0, minute=0, second=0, microsecond=0)
            storage = rows_by_key.get((endpoint_id, bucket_start), [])
            hot = any(
                row["storage_backend"] == "CLICKHOUSE" and row["storage_status"] == "HOT"
                for row in storage
            )
            if hot or not storage:
                hot_identities.append((event_id, endpoint_id, occurred_at))
                continue
            restored = next(
                (
                    row
                    for row in storage
                    if row["storage_backend"] == "S3" and row["storage_status"] == "RESTORED"
                ),
                None,
            )
            if restored is None:
                unavailable.add(rendered)
                continue
            group = (endpoint_id, bucket_start, str(restored["storage_path"]))
            restored_groups.setdefault(group, []).append(rendered)

        found = {
            str(row["event_id"]): _event_detail_dto(row)
            for row in self.events.details(hot_identities)
        }
        for (endpoint_id, bucket_start, storage_path), event_ids in restored_groups.items():
            for row in self.restored.read_rows(
                storage_path,
                columns=EVENT_DETAIL_COLUMNS,
                from_=bucket_start,
                to=bucket_start + timedelta(days=1),
                endpoint_id=endpoint_id,
                event_ids=event_ids,
            ):
                rendered = str(row["event_id"])
                if rendered in event_ids:
                    found[rendered] = _event_detail_dto(row)
        return found, unavailable

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


def _exact_bucket_count(
    bucket: dict[str, Any],
    *,
    query: EventListQuery,
    from_: datetime,
    to: datetime,
) -> int | None:
    if any(
        value is not None
        for value in (
            query.event_type,
            query.process_name,
            query.file_path,
            query.domain,
            query.remote_ip,
            query.dns_query,
            query.l7_protocol,
        )
    ):
        return None
    bucket_end = bucket.get("bucket_end_at")
    event_count = bucket.get("event_count")
    if bucket_end is None or event_count is None:
        return None
    if from_ <= _utc(bucket["bucket_start_at"]) and _utc(bucket_end) <= to:
        return int(event_count)
    return None


def _bucket_can_improve(bucket: dict[str, Any], worst_heap_key: int, sort_order: str) -> bool:
    if sort_order == "desc":
        boundary = bucket.get("bucket_end_at")
        if boundary is None:
            return True
        latest_exclusive = int(_utc(boundary).timestamp() * 1_000_000)
        return latest_exclusive > worst_heap_key
    earliest = int(_utc(bucket["bucket_start_at"]).timestamp() * 1_000_000)
    worst_occurred_at = -worst_heap_key
    return earliest <= worst_occurred_at


def _event_order_key(row: dict[str, Any]) -> tuple[int, int]:
    occurred_at = _utc(row["occurred_at"])
    occurred_key = int(occurred_at.timestamp() * 1_000_000)
    event_id = str(row["event_id"])
    try:
        event_key = UUID(event_id).int
    except ValueError:
        event_key = int.from_bytes(hashlib.sha256(event_id.encode()).digest(), "big")
    return occurred_key, event_key


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


class _RestoredDashboardAccumulator:
    DIMENSIONS = (
        ("process", "process_name", "top_processes"),
        ("remote_ip", "remote_ip", "top_remote_ips"),
        ("file_hash", "file_hash_sha256", "top_file_hashes"),
        ("dns_query", "dns_query", "top_dns_queries"),
        ("l7_protocol", "l7_protocol", "top_l7_protocols"),
    )

    def __init__(self, interval_seconds: int) -> None:
        self.interval_seconds = interval_seconds
        self.aggregate = DashboardEventAggregate()
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="edr-dashboard-")
        self.connection = sqlite3.connect(f"{self.temporary_directory.name}/aggregate.sqlite3")
        self.connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=FILE;
            CREATE TABLE seen_events (event_id TEXT PRIMARY KEY);
            CREATE TABLE dimensions (
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                PRIMARY KEY (kind, value)
            );
            """
        )

    def __enter__(self) -> "_RestoredDashboardAccumulator":
        return self

    def __exit__(self, *_args: object) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def add(self, row: dict[str, Any], occurred_at: datetime) -> None:
        inserted = self.connection.execute(
            "INSERT OR IGNORE INTO seen_events (event_id) VALUES (?)",
            (str(row["event_id"]),),
        )
        if inserted.rowcount != 1:
            return
        self.aggregate.total_count += 1
        if self.aggregate.total_count > MAX_RESTORED_DASHBOARD_EVENTS:
            raise ApplicationError(
                400,
                "VALIDATION_ERROR",
                "Restored archive dashboard range is too large; narrow the time range or Endpoint filter.",
            )
        self.aggregate.by_event_type[str(row["event_type"])] += 1
        epoch = int(occurred_at.timestamp())
        bucket_start_at = datetime.fromtimestamp(
            (epoch // self.interval_seconds) * self.interval_seconds,
            tz=UTC,
        )
        self.aggregate.time_series[bucket_start_at] += 1
        for kind, field, _target in self.DIMENSIONS:
            value = row.get(field)
            if value is not None and value != "":
                self._increment(kind, str(value))
        domain = row.get("remote_domain") or row.get("http_host")
        if domain is not None and domain != "":
            self._increment("domain", str(domain))

    def _increment(self, kind: str, value: str) -> None:
        self.connection.execute(
            """
            INSERT INTO dimensions (kind, value, event_count) VALUES (?, ?, 1)
            ON CONFLICT (kind, value) DO UPDATE SET event_count = event_count + 1
            """,
            (kind, value),
        )

    def result(self) -> DashboardEventAggregate:
        targets = self.DIMENSIONS + (("domain", "", "top_domains"),)
        for kind, _field, target in targets:
            rows = self.connection.execute(
                """
                SELECT value, event_count FROM dimensions
                WHERE kind = ?
                ORDER BY event_count DESC, value ASC
                LIMIT 10
                """,
                (kind,),
            ).fetchall()
            getattr(self.aggregate, target).update({str(value): int(count) for value, count in rows})
        return self.aggregate


def _merge_dashboard_aggregate(target: DashboardEventAggregate, source: DashboardEventAggregate) -> None:
    target.total_count += source.total_count
    for field in (
        "by_event_type",
        "top_processes",
        "top_remote_ips",
        "top_domains",
        "top_file_hashes",
        "top_dns_queries",
        "top_l7_protocols",
        "time_series",
    ):
        getattr(target, field).update(getattr(source, field))


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


def _ensure_archive_rows_ready(metadata_rows: list[dict[str, Any]]) -> set[tuple[int, datetime]]:
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
    return hot_keys
