from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

import boto3
import pyarrow.parquet as pq
import pytest
from botocore.stub import Stubber

from backend.archive_lifecycle import BotoParquetArchiveStore, StorageLifecycleWorker
from backend.archive_service import (
    ArchiveService,
    BotoRestoreObjectClient,
    RestoreObjectStatus,
)
from backend.contracts.archives import ArchiveRestoreRequest
from backend.storage.clickhouse import EVENT_COLUMNS

NOW = datetime(2026, 7, 19, 12, tzinfo=UTC)


class MemoryS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.requests: list[dict] = []

    def put_object(self, **request):
        self.requests.append(dict(request))
        self.objects[request["Key"]] = request["Body"].read()
        self.metadata[request["Key"]] = dict(request["Metadata"])

    def head_object(self, *, Bucket, Key):
        assert Bucket == "archive"
        return {
            "ContentLength": len(self.objects[Key]),
            "Metadata": self.metadata[Key],
        }


def _event_row() -> dict:
    row = dict.fromkeys(EVENT_COLUMNS)
    row.update(
        {
            "event_id": UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e001"),
            "batch_id": UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e000"),
            "endpoint_id": 7,
            "agent_id": "agent-7",
            "hostname": "ENDPOINT-7",
            "os_type": "MACOS",
            "event_type": "DNS_QUERY",
            "occurred_at": NOW - timedelta(days=1),
            "ingested_at": NOW - timedelta(days=1),
            "raw_payload": "{}",
            "payload_sha256": b"a" * 64,
            "schema_version": 1,
            "created_at": NOW - timedelta(days=1),
            "updated_at": NOW - timedelta(days=1),
            "is_delete": 0,
        }
    )
    return row


def test_parquet_archive_store_streams_verifies_and_uses_glacier() -> None:
    s3 = MemoryS3()
    stored = BotoParquetArchiveStore(s3, bucket="archive").write(
        "archives/date=2026-07-18/endpoint_id=7/events.parquet",
        [[_event_row()]],
        expected_count=1,
    )

    assert stored.event_count == 1
    assert stored.size_bytes == len(s3.objects[stored.storage_path])
    assert len(stored.checksum_sha256) == 64
    assert s3.requests[0]["StorageClass"] == "GLACIER"
    table = pq.read_table(BytesIO(s3.objects[stored.storage_path]))
    assert table.num_rows == 1
    assert table.column("event_id")[0].as_py() == "018ff8f4-86de-7b25-9b8a-2d22f6a3e001"


def test_parquet_archive_store_rejects_count_mismatch_before_upload() -> None:
    s3 = MemoryS3()
    with pytest.raises(RuntimeError, match="row count mismatch"):
        BotoParquetArchiveStore(s3, bucket="archive").write("archive.parquet", [[_event_row()]], expected_count=2)
    assert s3.requests == []


def test_restore_status_parses_ongoing_and_expiry_headers() -> None:
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    with Stubber(client) as stubber:
        stubber.add_response(
            "head_object",
            {"Restore": 'ongoing-request="true"'},
            {"Bucket": "archive", "Key": "pending.parquet"},
        )
        stubber.add_response(
            "head_object",
            {"Restore": 'ongoing-request="false", expiry-date="Sun, 26 Jul 2026 00:00:00 GMT"'},
            {"Bucket": "archive", "Key": "restored.parquet"},
        )
        restore = BotoRestoreObjectClient(client, bucket="archive")
        assert restore.status("pending.parquet") == RestoreObjectStatus(ongoing=True)
        assert restore.status("restored.parquet") == RestoreObjectStatus(
            ongoing=False,
            expires_at=datetime(2026, 7, 26, tzinfo=UTC),
        )


def test_restore_claims_database_before_s3_and_marks_dispatch_failure() -> None:
    calls: list[str] = []

    class Repository:
        def restore_buckets(self, *_args):
            return [
                {
                    "endpoint_id": 7,
                    "bucket_start_at": NOW - timedelta(days=2),
                    "bucket_end_at": NOW - timedelta(days=1),
                    "storage_backend": "S3",
                    "storage_class": "GLACIER_FLEXIBLE_RETRIEVAL",
                    "storage_status": "ARCHIVED",
                    "storage_path": "archive.parquet",
                    "event_count": 1,
                }
            ]

        def request_restore(self, **_kwargs):
            calls.append("claim")
            return True

        def mark_restore_failed(self, **_kwargs):
            calls.append("failed")
            return True

    class Restore:
        def restore(self, _key):
            calls.append("restore")
            raise RuntimeError("dispatch failed")

    request = ArchiveRestoreRequest.model_validate(
        {
            "endpointIds": [7],
            "from": NOW - timedelta(days=2),
            "to": NOW - timedelta(days=1),
        }
    )
    with pytest.raises(RuntimeError, match="dispatch failed"):
        ArchiveService(Repository(), Restore()).start_restore(
            request,
            actor_identifier="admin",
            request_id="request-1",
            now=NOW,
        )
    assert calls == ["claim", "restore", "failed"]


def test_lifecycle_marks_completed_restore_and_expires_old_copies() -> None:
    class Metadata:
        def archive_candidates(self, **_kwargs):
            return []

        def requested_restores(self, **_kwargs):
            return [
                {
                    "endpoint_id": 7,
                    "bucket_start_at": NOW - timedelta(days=2),
                    "storage_path": "archive.parquet",
                    "restore_requested_at": NOW - timedelta(hours=1),
                }
            ]

        def mark_restored(self, **kwargs):
            self.restored = kwargs
            return True

        def expire_restores(self, _now):
            return 2

        def partition_deletion_candidates(self, **_kwargs):
            return []

    class Restore:
        def status(self, _key):
            return RestoreObjectStatus(False, NOW + timedelta(days=7))

        def restore(self, _key):
            pytest.fail("completed restore must not be dispatched again")

    metadata = Metadata()
    result = StorageLifecycleWorker(
        metadata=metadata,
        events=object(),
        archive_store=object(),
        restore_client=Restore(),
    ).run_once(now=NOW)
    assert result.restored_bucket_count == 1
    assert result.expired_bucket_count == 2
    assert metadata.restored["restore_expires_at"] == NOW + timedelta(days=7)


def test_lifecycle_exports_under_archive_guard_and_records_verified_object() -> None:
    bucket_start = NOW.replace(hour=0) - timedelta(days=1)

    class Metadata:
        def archive_candidates(self, **_kwargs):
            return [{"endpoint_id": 7, "bucket_start_at": bucket_start, "archive_storage_path": None}]

        @contextmanager
        def archive_guard(self, **_kwargs):
            yield {"bucket_end_at": bucket_start + timedelta(days=1)}

        def record_verified_archive(self, **kwargs):
            self.archive = kwargs

        def requested_restores(self, **_kwargs):
            return []

        def expire_restores(self, _now):
            return 0

        def partition_deletion_candidates(self, **_kwargs):
            return []

    class Events:
        def archive_count(self, **_kwargs):
            return 1

        def archive_row_batches(self, **_kwargs):
            return [[_event_row()]]

    metadata = Metadata()
    result = StorageLifecycleWorker(
        metadata=metadata,
        events=Events(),
        archive_store=BotoParquetArchiveStore(MemoryS3(), bucket="archive", use_glacier_storage_class=False),
        restore_client=object(),
    ).run_once(now=NOW)
    assert result.archived_bucket_count == 1
    assert metadata.archive["event_count"] == 1
    assert metadata.archive["storage_path"].endswith("endpoint_id=7/events.parquet")
