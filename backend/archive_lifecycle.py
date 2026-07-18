import hashlib
import logging
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq

from .archive_service import RestoreStatusPort
from .storage.clickhouse import EVENT_COLUMNS, EventRepository
from .storage.postgres import IngestMetadataRepository

LOGGER = logging.getLogger(__name__)
ARCHIVE_SAFETY_WINDOW = timedelta(days=7)
RESTORE_REDISPATCH_GRACE = timedelta(minutes=15)
RESTORE_TIMEOUT = timedelta(days=2)


@dataclass(frozen=True, slots=True)
class ArchivedObject:
    storage_path: str
    event_count: int
    size_bytes: int
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    archived_bucket_count: int
    restored_bucket_count: int
    expired_bucket_count: int
    deleted_partition_count: int


EVENT_ARCHIVE_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string(), nullable=False),
        pa.field("batch_id", pa.string()),
        pa.field("endpoint_id", pa.uint64(), nullable=False),
        pa.field("agent_id", pa.string(), nullable=False),
        pa.field("hostname", pa.string(), nullable=False),
        pa.field("os_type", pa.string(), nullable=False),
        pa.field("ip_address", pa.string()),
        pa.field("event_type", pa.string(), nullable=False),
        pa.field("occurred_at", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("ingested_at", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("process_name", pa.string()),
        pa.field("process_path", pa.string()),
        pa.field("pid", pa.uint64()),
        pa.field("ppid", pa.uint64()),
        pa.field("command_line", pa.string()),
        pa.field("user_name", pa.string()),
        pa.field("file_path", pa.string()),
        pa.field("file_action", pa.string()),
        pa.field("file_hash_sha256", pa.string()),
        pa.field("remote_ip", pa.string()),
        pa.field("remote_domain", pa.string()),
        pa.field("remote_port", pa.uint16()),
        pa.field("protocol", pa.string()),
        pa.field("dns_query", pa.string()),
        pa.field("dns_record_type", pa.string()),
        pa.field("dns_response_code", pa.string()),
        pa.field("dns_answers_json", pa.string()),
        pa.field("l7_protocol", pa.string()),
        pa.field("http_method", pa.string()),
        pa.field("http_host", pa.string()),
        pa.field("url", pa.string()),
        pa.field("http_status_code", pa.uint16()),
        pa.field("http_user_agent", pa.string()),
        pa.field("tls_sni", pa.string()),
        pa.field("tls_version", pa.string()),
        pa.field("tls_certificate_subject", pa.string()),
        pa.field("tls_certificate_issuer", pa.string()),
        pa.field("tls_certificate_sha256", pa.string()),
        pa.field("raw_payload", pa.string(), nullable=False),
        pa.field("payload_sha256", pa.string(), nullable=False),
        pa.field("schema_version", pa.uint16(), nullable=False),
        pa.field("created_at", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("updated_at", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("is_delete", pa.uint8(), nullable=False),
    ]
)

if EVENT_ARCHIVE_SCHEMA.names != EVENT_COLUMNS:
    raise RuntimeError("Archive Parquet schema must match ClickHouse event columns")


class BotoParquetArchiveStore:
    def __init__(self, s3_client: Any, *, bucket: str, use_glacier_storage_class: bool = True) -> None:
        self.s3 = s3_client
        self.bucket = bucket
        self.use_glacier_storage_class = use_glacier_storage_class

    def write(
        self,
        storage_path: str,
        batches: Iterable[list[dict[str, Any]]],
        *,
        expected_count: int,
    ) -> ArchivedObject:
        written = 0
        with tempfile.TemporaryFile() as target:
            with pq.ParquetWriter(target, EVENT_ARCHIVE_SCHEMA, compression="zstd") as writer:
                for batch in batches:
                    if not batch:
                        continue
                    normalized = [
                        {column: _parquet_value(row.get(column)) for column in EVENT_COLUMNS}
                        for row in batch
                    ]
                    writer.write_table(pa.Table.from_pylist(normalized, schema=EVENT_ARCHIVE_SCHEMA))
                    written += len(normalized)
            if written != expected_count:
                raise RuntimeError(
                    f"Archive row count mismatch: ClickHouse count={expected_count}, Parquet rows={written}"
                )
            size_bytes = target.tell()
            target.seek(0)
            digest = hashlib.sha256()
            while chunk := target.read(1024 * 1024):
                digest.update(chunk)
            checksum = digest.hexdigest()
            target.seek(0)
            request: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": storage_path,
                "Body": target,
                "ContentType": "application/vnd.apache.parquet",
                "Metadata": {"sha256": checksum, "event-count": str(written)},
            }
            if self.use_glacier_storage_class:
                request["StorageClass"] = "GLACIER"
            self.s3.put_object(**request)
        durable = self.s3.head_object(Bucket=self.bucket, Key=storage_path)
        if int(durable.get("ContentLength", -1)) != size_bytes:
            raise RuntimeError("Archive object length verification failed")
        metadata = durable.get("Metadata", {})
        if metadata.get("sha256") != checksum or metadata.get("event-count") != str(written):
            raise RuntimeError("Archive object metadata verification failed")
        return ArchivedObject(storage_path, written, size_bytes, checksum)


class StorageLifecycleWorker:
    def __init__(
        self,
        *,
        metadata: IngestMetadataRepository,
        events: EventRepository,
        archive_store: BotoParquetArchiveStore,
        restore_client: RestoreStatusPort,
        candidate_limit: int = 10,
    ) -> None:
        self.metadata = metadata
        self.events = events
        self.archive_store = archive_store
        self.restore_client = restore_client
        self.candidate_limit = candidate_limit

    def run_once(self, *, now: datetime) -> LifecycleResult:
        now = now.astimezone(UTC)
        completed_before = now.replace(hour=0, minute=0, second=0, microsecond=0)
        archived = self._archive_completed_buckets(completed_before=completed_before, now=now)
        restored = self._refresh_restores(now=now)
        expired = self.metadata.expire_restores(now)
        deleted = self._delete_verified_partitions(now=now)
        return LifecycleResult(archived, restored, expired, deleted)

    def _archive_completed_buckets(self, *, completed_before: datetime, now: datetime) -> int:
        archived = 0
        candidates = self.metadata.archive_candidates(
            completed_before=completed_before,
            limit=self.candidate_limit,
        )
        for candidate in candidates:
            endpoint_id = int(candidate["endpoint_id"])
            bucket_start_at = _utc(candidate["bucket_start_at"])
            try:
                with self.metadata.archive_guard(
                    endpoint_id=endpoint_id,
                    bucket_start_at=bucket_start_at,
                ) as hot:
                    if hot is None:
                        continue
                    event_count = self.events.archive_count(
                        endpoint_id=endpoint_id,
                        bucket_start_at=bucket_start_at,
                    )
                    if event_count <= 0:
                        LOGGER.warning(
                            "archive candidate has no active events endpoint_id=%s bucket=%s",
                            endpoint_id,
                            bucket_start_at.isoformat(),
                        )
                        continue
                    storage_path = str(
                        candidate.get("archive_storage_path") or _archive_key(endpoint_id, bucket_start_at)
                    )
                    archived_object = self.archive_store.write(
                        storage_path,
                        self.events.archive_row_batches(
                            endpoint_id=endpoint_id,
                            bucket_start_at=bucket_start_at,
                        ),
                        expected_count=event_count,
                    )
                    self.metadata.record_verified_archive(
                        endpoint_id=endpoint_id,
                        bucket_start_at=bucket_start_at,
                        bucket_end_at=_utc(hot["bucket_end_at"]),
                        storage_path=archived_object.storage_path,
                        event_count=archived_object.event_count,
                        size_bytes=archived_object.size_bytes,
                        checksum_sha256=archived_object.checksum_sha256,
                        verified_at=now,
                    )
                    archived += 1
            except Exception:
                LOGGER.exception(
                    "archive export failed endpoint_id=%s bucket=%s",
                    endpoint_id,
                    bucket_start_at.isoformat(),
                )
        return archived

    def _refresh_restores(self, *, now: datetime) -> int:
        restored = 0
        for row in self.metadata.requested_restores(limit=self.candidate_limit * 10):
            endpoint_id = int(row["endpoint_id"])
            bucket_start_at = _utc(row["bucket_start_at"])
            requested_at = _utc(row["restore_requested_at"] or now)
            try:
                status = self.restore_client.status(str(row["storage_path"]))
                if status is None:
                    if now - requested_at >= RESTORE_TIMEOUT:
                        self.metadata.mark_restore_failed(
                            endpoint_id=endpoint_id,
                            bucket_start_at=bucket_start_at,
                            error="S3 did not report a restore request before the lifecycle timeout.",
                            failed_at=now,
                        )
                    elif now - requested_at >= RESTORE_REDISPATCH_GRACE:
                        self.restore_client.restore(str(row["storage_path"]))
                    continue
                if status.ongoing:
                    continue
                if status.expires_at is None:
                    raise RuntimeError("Completed restore status has no expiry time")
                if self.metadata.mark_restored(
                    endpoint_id=endpoint_id,
                    bucket_start_at=bucket_start_at,
                    restored_at=now,
                    restore_expires_at=status.expires_at,
                ):
                    restored += 1
            except Exception as error:
                if now - requested_at >= RESTORE_TIMEOUT:
                    self.metadata.mark_restore_failed(
                        endpoint_id=endpoint_id,
                        bucket_start_at=bucket_start_at,
                        error=f"{type(error).__name__}: {error}"[:1000],
                        failed_at=now,
                    )
                else:
                    LOGGER.exception(
                        "restore status probe failed endpoint_id=%s bucket=%s",
                        endpoint_id,
                        bucket_start_at.isoformat(),
                    )
        return restored

    def _delete_verified_partitions(self, *, now: datetime) -> int:
        deleted = 0
        verified_before = now - ARCHIVE_SAFETY_WINDOW
        for bucket_start_at in self.metadata.partition_deletion_candidates(
            verified_before=verified_before,
            limit=self.candidate_limit,
        ):
            bucket_start_at = _utc(bucket_start_at)
            if not self.metadata.claim_partition_deletion(
                bucket_start_at=bucket_start_at,
                verified_before=verified_before,
                now=now,
            ):
                continue
            try:
                self.events.drop_partition(bucket_start_at.date())
            except Exception:
                LOGGER.exception("ClickHouse partition deletion failed bucket=%s", bucket_start_at.isoformat())
                continue
            self.metadata.mark_partition_deleted(bucket_start_at=bucket_start_at, deleted_at=now)
            deleted += 1
        return deleted


def _archive_key(endpoint_id: int, bucket_start_at: datetime) -> str:
    bucket_date = bucket_start_at.astimezone(UTC).date().isoformat()
    return f"archives/date={bucket_date}/endpoint_id={endpoint_id}/events.parquet"


def _parquet_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("ascii")
    if isinstance(value, datetime):
        return _utc(value)
    return value


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
