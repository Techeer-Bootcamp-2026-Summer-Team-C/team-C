from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

import backend.event_service as event_service_module
from backend.contracts.requests import EventListQuery
from backend.errors import ApplicationError
from backend.event_service import EventService, RestoredEventReader
from backend.storage.clickhouse import EVENT_COLUMNS

NOW = datetime(2026, 7, 19, tzinfo=UTC)


def event_row(index: int, *, endpoint_id: int = 1, minute: int | None = None) -> dict[str, object]:
    row: dict[str, object] = {column: None for column in EVENT_COLUMNS}
    row.update(
        event_id=UUID(int=index + 1),
        batch_id=UUID(int=10_000 + index),
        endpoint_id=endpoint_id,
        agent_id=f"agent-{endpoint_id}",
        hostname=f"endpoint-{endpoint_id}",
        os_type="WINDOWS",
        event_type="PROCESS_EXECUTION",
        occurred_at=NOW + timedelta(minutes=index if minute is None else minute),
        ingested_at=NOW + timedelta(minutes=index if minute is None else minute),
        dns_answers_json="[]",
        is_delete=0,
    )
    return row


class Events:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = sorted(rows, key=lambda row: row["occurred_at"], reverse=True)
        self.search_arguments: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.search_arguments.append(kwargs)
        offset = int(kwargs.get("offset", 0))
        limit = int(kwargs.get("limit", len(self.rows)))
        return self.rows[offset : offset + limit]

    def count_search(self, **_kwargs):
        return len(self.rows)


class Metadata:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []

    def overlapping_all(self, **_kwargs):
        return self.rows


def test_hot_event_list_uses_database_limit_offset_and_count() -> None:
    events = Events([event_row(index) for index in range(8)])
    service = EventService(
        events=events,
        metadata=Metadata(),
        restored=SimpleNamespace(read_rows=lambda _path, **_filters: pytest.fail("archive should not be read")),
    )

    items, total = service.list_rows(
        EventListQuery(page=2, size=3),
        from_=NOW,
        to=NOW + timedelta(days=1),
    )

    assert total == 8
    assert events.search_arguments[0]["limit"] == 3
    assert events.search_arguments[0]["offset"] == 3
    assert [item.event_id for item in items] == [str(UUID(int=5)), str(UUID(int=4)), str(UUID(int=3))]


def test_restored_events_merge_with_bounded_page_window() -> None:
    events = Events([event_row(100, minute=100), event_row(99, minute=99)])
    restored_rows = [event_row(index) for index in range(20)]
    metadata = Metadata(
        [
            {
                "endpoint_id": 1,
                "bucket_start_at": NOW,
                "storage_backend": "S3",
                "storage_status": "RESTORED",
                "storage_path": "restored/events.parquet",
            }
        ]
    )
    service = EventService(
        events=events,
        metadata=metadata,
        restored=SimpleNamespace(read_rows=lambda _path, **_filters: iter(restored_rows)),
    )

    items, total = service.list_rows(
        EventListQuery(page=2, size=3),
        from_=NOW,
        to=NOW + timedelta(days=1),
    )

    assert total == 22
    assert events.search_arguments[0]["limit"] == 6
    assert [item.event_id for item in items] == [str(UUID(int=19)), str(UUID(int=18)), str(UUID(int=17))]


def test_restored_archive_rejects_unbounded_deep_page() -> None:
    metadata = Metadata(
        [
            {
                "endpoint_id": 1,
                "bucket_start_at": NOW,
                "storage_backend": "S3",
                "storage_status": "RESTORED",
                "storage_path": "restored/events.parquet",
            }
        ]
    )
    service = EventService(
        events=Events([]),
        metadata=metadata,
        restored=SimpleNamespace(read_rows=lambda _path, **_filters: []),
    )

    with pytest.raises(ApplicationError, match="pagination") as caught:
        service.list_rows(EventListQuery(page=22, size=500), from_=NOW, to=NOW + timedelta(days=1))

    assert caught.value.status_code == 400


def test_restored_page_uses_bucket_counts_and_skips_older_parquet_scan() -> None:
    older = {
        "endpoint_id": 1,
        "bucket_start_at": NOW,
        "bucket_end_at": NOW + timedelta(days=1),
        "event_count": 10,
        "storage_backend": "S3",
        "storage_status": "RESTORED",
        "storage_path": "older.parquet",
    }
    newer = {
        "endpoint_id": 1,
        "bucket_start_at": NOW + timedelta(days=1),
        "bucket_end_at": NOW + timedelta(days=2),
        "event_count": 2,
        "storage_backend": "S3",
        "storage_status": "RESTORED",
        "storage_path": "newer.parquet",
    }
    read_paths: list[str] = []

    def read_rows(path, **_filters):
        read_paths.append(path)
        assert path == "newer.parquet"
        return iter([event_row(1, minute=24 * 60 + 20), event_row(2, minute=24 * 60 + 10)])

    service = EventService(
        events=Events([]),
        metadata=Metadata([older, newer]),
        restored=SimpleNamespace(read_rows=read_rows),
    )

    items, total = service.list_rows(EventListQuery(page=1, size=2), from_=NOW, to=NOW + timedelta(days=2))

    assert len(items) == 2
    assert total == 12
    assert read_paths == ["newer.parquet"]


def test_parquet_reader_yields_bounded_batches_lazily(monkeypatch) -> None:
    yielded_batches: list[int] = []

    class Dataset:
        def scanner(self, *, columns, filter, batch_size, use_threads):
            assert columns == ["event_id"]
            assert filter is not None
            assert batch_size == 1_024
            assert use_threads is False

            class Scanner:
                def to_batches(self):
                    yielded_batches.append(1)
                    yield SimpleNamespace(to_pylist=lambda: [{"event_id": "first"}])
                    yielded_batches.append(2)
                    yield SimpleNamespace(to_pylist=lambda: [{"event_id": "second"}])

            return Scanner()

    monkeypatch.setattr(event_service_module.pads, "dataset", lambda *_args, **_kwargs: Dataset())
    reader = object.__new__(RestoredEventReader)
    reader.bucket = "archive"
    reader.filesystem = object()

    rows = reader.read_rows("events.parquet", columns=["event_id"], endpoint_id=1)

    assert next(rows) == {"event_id": "first"}
    assert yielded_batches == [1]
    assert list(rows) == [{"event_id": "second"}]


def test_event_detail_bulk_groups_hot_restored_and_unavailable_buckets() -> None:
    hot_row = event_row(1, endpoint_id=1)
    restored_row = event_row(2, endpoint_id=2)
    for row in (hot_row, restored_row):
        row["raw_payload"] = "{}"
        row["payload_sha256"] = "a" * 64
        row["schema_version"] = 1

    class BulkEvents:
        def __init__(self):
            self.identities = []

        def details(self, identities):
            self.identities = identities
            return [hot_row]

    read_filters = []

    def read_rows(_path, **filters):
        read_filters.append(filters)
        return [restored_row]

    metadata = Metadata(
        [
            {
                "endpoint_id": 1,
                "bucket_start_at": NOW,
                "storage_backend": "CLICKHOUSE",
                "storage_status": "HOT",
            },
            {
                "endpoint_id": 2,
                "bucket_start_at": NOW,
                "storage_backend": "S3",
                "storage_status": "RESTORED",
                "storage_path": "restored.parquet",
            },
            {
                "endpoint_id": 3,
                "bucket_start_at": NOW,
                "storage_backend": "S3",
                "storage_status": "ARCHIVED",
                "storage_path": "archived.parquet",
            },
        ]
    )
    events = BulkEvents()
    identities = [
        (UUID(str(hot_row["event_id"])), 1, NOW),
        (UUID(str(restored_row["event_id"])), 2, NOW),
        (UUID(int=4), 3, NOW),
    ]
    found, unavailable = EventService(
        events=events,
        metadata=metadata,
        restored=SimpleNamespace(read_rows=read_rows),
    ).details_bulk(identities)

    assert set(found) == {str(hot_row["event_id"]), str(restored_row["event_id"])}
    assert unavailable == {str(UUID(int=4))}
    assert len(events.identities) == 1
    assert read_filters[0]["event_ids"] == [str(restored_row["event_id"])]
