import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.contracts.enums import DashboardEventSource, DashboardInterval
from backend.contracts.requests import DashboardSummaryQuery
from backend.errors import ApplicationError
from backend.kafka import ConsumedMessage
from backend.rollup import DashboardRollupSynchronizer, DashboardRollupWorker, RollupRefreshResult
from backend.storage.clickhouse import DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS, EventRepository
from backend.summary_service import SummaryService
from tools import run_dashboard_rollup_worker as rollup_cli

NOW = datetime(2026, 7, 20, 12, 5, tzinfo=UTC)


def message(*, offset: int, occurred_at: datetime = NOW, partition: int = 0) -> ConsumedMessage:
    payload = {
        "event": {
            "endpoint_id": 7,
            "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
        }
    }
    return ConsumedMessage(
        topic="telemetry.validated",
        partition=partition,
        offset=offset,
        key=b"7",
        value=json.dumps(payload).encode(),
        headers=[],
    )


class Consumer:
    def __init__(self, messages: list[ConsumedMessage]) -> None:
        self.messages = list(messages)
        self.committed: list[ConsumedMessage] = []
        self.rewound: list[ConsumedMessage] = []

    def consume_one(self, _timeout: float = 1.0) -> ConsumedMessage | None:
        return self.messages.pop(0) if self.messages else None

    def commit(self, item: ConsumedMessage) -> None:
        self.committed.append(item)

    def rewind(self, item: ConsumedMessage) -> None:
        self.rewound.append(item)


class Store:
    def __init__(self) -> None:
        self.bucket_calls: list[dict] = []
        self.range_calls: list[dict] = []

    def replace_buckets(self, **kwargs) -> None:
        self.bucket_calls.append(kwargs)

    def replace_range(self, **kwargs) -> None:
        self.range_calls.append(kwargs)


class FrozenStore(Store):
    def __init__(self, *frozen_dates) -> None:
        super().__init__()
        self.frozen_dates = set(frozen_dates)
        self.guarded_dates: list[set] = []

    @contextmanager
    def writer_guard(self, *, bucket_dates):
        self.guarded_dates.append(set(bucket_dates))
        yield

    def frozen_bucket_dates(self, *, bucket_dates):
        return set(bucket_dates) & self.frozen_dates


class Events:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def dashboard_rollup_rows(self, **kwargs):
        self.calls.append(kwargs)
        endpoint_id = kwargs["endpoint_ids"][0]
        bucket = kwargs["from_"]
        return (
            [
                {
                    "endpoint_id": endpoint_id,
                    "bucket_start_at": bucket,
                    "event_type": "PROCESS_EXECUTION",
                    "event_count": 1,
                    "source_max_ingested_at": NOW,
                }
            ],
            [
                {
                    "endpoint_id": endpoint_id,
                    "bucket_start_at": bucket,
                    "dimension_name": "top_processes",
                    "dimension_value": "powershell.exe",
                    "event_count": 1,
                }
            ],
        )


def test_dashboard_query_uses_rollup_by_default_and_allows_explicit_live_reads() -> None:
    assert DashboardSummaryQuery(interval="5m").event_source is DashboardEventSource.ROLLUP
    assert DashboardSummaryQuery(interval="5m", eventSource="LIVE").event_source is DashboardEventSource.LIVE


def test_worker_coalesces_duplicate_bucket_messages_and_commits_only_latest_partition_offset() -> None:
    consumer = Consumer([message(offset=10), message(offset=11)])

    class Synchronizer:
        calls: list[set[tuple[int, datetime]]] = []

        def refresh_buckets(self, keys):
            self.calls.append(set(keys))
            return RollupRefreshResult(1, 1, 1, NOW)

    synchronizer = Synchronizer()
    worker = DashboardRollupWorker(
        consumer=consumer,
        synchronizer=synchronizer,
        flush_interval_seconds=60,
        clock=lambda: 0,
    )

    assert worker.run_once()
    assert worker.run_once()
    result = worker.flush()

    assert result is not None
    assert synchronizer.calls == [{(7, NOW.replace(second=0, microsecond=0))}]
    assert [item.offset for item in consumer.committed] == [11]
    assert worker.dirty_buckets == set()


def test_worker_keeps_dirty_buckets_and_offsets_uncommitted_when_projection_write_fails() -> None:
    consumer = Consumer([message(offset=10)])

    class Synchronizer:
        def refresh_buckets(self, _keys):
            raise RuntimeError("PostgreSQL unavailable")

    worker = DashboardRollupWorker(
        consumer=consumer,
        synchronizer=Synchronizer(),
        flush_interval_seconds=60,
        clock=lambda: 0,
    )
    assert worker.run_once()

    with pytest.raises(RuntimeError, match="PostgreSQL unavailable"):
        worker.flush()

    assert consumer.committed == []
    assert worker.dirty_buckets == {(7, NOW.replace(second=0, microsecond=0))}
    assert worker.pending_offsets[("telemetry.validated", 0)].offset == 10


def test_worker_quarantines_poison_message_after_flushing_earlier_offsets() -> None:
    valid = message(offset=10)
    invalid = ConsumedMessage(
        topic="telemetry.validated",
        partition=0,
        offset=11,
        key=b"7",
        value=b"not-json",
        headers=[],
    )
    consumer = Consumer([valid, invalid])

    class Synchronizer:
        def __init__(self) -> None:
            self.calls = 0

        def refresh_buckets(self, _keys):
            self.calls += 1
            return RollupRefreshResult(1, 1, 0, NOW)

    class Sink:
        def __init__(self) -> None:
            self.calls: list[tuple[ConsumedMessage, dict]] = []

        def record(self, item, **kwargs):
            self.calls.append((item, kwargs))

    synchronizer = Synchronizer()
    sink = Sink()
    worker = DashboardRollupWorker(
        consumer=consumer,
        synchronizer=synchronizer,
        failure_sink=sink,
        flush_interval_seconds=60,
        clock=lambda: 0,
        now=lambda: NOW,
    )

    assert worker.run_once()
    assert worker.run_once()

    assert synchronizer.calls == 1
    assert [item.offset for item in consumer.committed] == [10, 11]
    assert sink.calls[0][0].offset == 11
    assert sink.calls[0][1]["failure_stage"] == "DASHBOARD_ROLLUP"
    assert sink.calls[0][1]["failure_code"] == "INVALID_MESSAGE"
    assert sink.calls[0][1]["retryable"] is False


def test_worker_rewinds_poison_message_when_failure_persistence_fails() -> None:
    invalid = ConsumedMessage(
        topic="telemetry.validated",
        partition=0,
        offset=12,
        key=None,
        value=b"[]",
        headers=[],
    )
    consumer = Consumer([invalid])

    class Sink:
        def record(self, *_args, **_kwargs):
            raise RuntimeError("failure sink unavailable")

    worker = DashboardRollupWorker(
        consumer=consumer,
        synchronizer=SimpleNamespace(),
        failure_sink=Sink(),
    )

    with pytest.raises(RuntimeError, match="failure sink unavailable"):
        worker.run_once()

    assert consumer.committed == []
    assert [item.offset for item in consumer.rewound] == [12]


def test_synchronizer_recomputes_contiguous_minute_segments_and_replaces_requested_buckets() -> None:
    events = Events()
    store = Store()
    synchronizer = DashboardRollupSynchronizer(events=events, store=store, now=lambda: NOW)
    keys = {
        (7, NOW.replace(minute=0)),
        (7, NOW.replace(minute=1)),
        (7, NOW.replace(minute=3)),
        (8, NOW.replace(minute=0)),
    }

    result = synchronizer.refresh_buckets(keys)

    assert result.bucket_count == 4
    assert len(events.calls) == 1
    assert events.calls[0]["from_"] == NOW.replace(minute=0)
    assert events.calls[0]["to"] == NOW.replace(minute=4)
    assert events.calls[0]["endpoint_ids"] == [7, 8]
    assert store.bucket_calls[0]["bucket_keys"] == keys
    assert store.bucket_calls[0]["dimension_bucket_keys"] == {
        (7, NOW.replace(minute=0, second=0, microsecond=0)),
        (8, NOW.replace(minute=0, second=0, microsecond=0)),
    }


def test_synchronizer_preserves_frozen_buckets_and_worker_can_commit_stale_signal() -> None:
    bucket = NOW.replace(second=0, microsecond=0)
    events = Events()
    store = FrozenStore(bucket.date())
    synchronizer = DashboardRollupSynchronizer(events=events, store=store, now=lambda: NOW)
    consumer = Consumer([message(offset=20, occurred_at=bucket)])
    worker = DashboardRollupWorker(
        consumer=consumer,
        synchronizer=synchronizer,
        flush_interval_seconds=60,
        clock=lambda: 0,
    )

    assert worker.run_once()
    result = worker.flush()

    assert result == RollupRefreshResult(0, 0, 0, NOW, 1)
    assert events.calls == []
    assert store.bucket_calls == []
    assert [item.offset for item in consumer.committed] == [20]
    assert store.guarded_dates == [{bucket.date()}]


def test_range_refresh_skips_frozen_days_without_recording_false_coverage() -> None:
    from_ = datetime(2026, 7, 19, 23, 0, tzinfo=UTC)
    to = datetime(2026, 7, 21, 1, 0, tzinfo=UTC)
    frozen_date = datetime(2026, 7, 20, tzinfo=UTC).date()

    class EmptyEvents:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def dashboard_rollup_rows(self, **kwargs):
            self.calls.append(kwargs)
            return [], []

    events = EmptyEvents()
    store = FrozenStore(frozen_date)
    result = DashboardRollupSynchronizer(events=events, store=store, now=lambda: NOW).refresh_range(
        from_=from_,
        to=to,
    )

    assert [(call["from_"], call["to"]) for call in events.calls] == [
        (from_, datetime(2026, 7, 20, tzinfo=UTC)),
        (datetime(2026, 7, 21, tzinfo=UTC), to),
    ]
    assert [(call["from_"], call["to"]) for call in store.range_calls] == [
        (from_, datetime(2026, 7, 20, tzinfo=UTC)),
        (datetime(2026, 7, 21, tzinfo=UTC), to),
    ]
    assert result.skipped_bucket_count == 24 * 60


def test_synchronizer_rejects_partial_minute_range_replacements() -> None:
    synchronizer = DashboardRollupSynchronizer(events=Events(), store=Store(), now=lambda: NOW)

    with pytest.raises(ValueError, match="minute boundaries"):
        synchronizer.refresh_range(from_=NOW + timedelta(seconds=1), to=NOW + timedelta(minutes=1))


def test_rollup_dashboard_rejects_uncovered_ranges_before_returning_false_zeroes() -> None:
    checked: list[tuple[datetime, datetime]] = []
    rollups = SimpleNamespace(
        covers_range=lambda *, from_, to: checked.append((from_, to)) or False,
    )
    service = SummaryService(
        endpoints=SimpleNamespace(),
        alerts=SimpleNamespace(),
        incidents=SimpleNamespace(),
        metadata=SimpleNamespace(),
        events=SimpleNamespace(),
        failures=SimpleNamespace(),
        event_service=SimpleNamespace(),
        event_rollups=rollups,
    )

    with pytest.raises(ApplicationError) as captured:
        service.dashboard(
            from_=NOW - timedelta(hours=1),
            to=NOW,
            interval=DashboardInterval.FIVE_MINUTES,
            calculated_at=NOW,
            event_source=DashboardEventSource.ROLLUP,
        )

    assert captured.value.status_code == 503
    assert captured.value.code == "ROLLUP_NOT_READY"
    assert captured.value.retryable is True
    assert checked == [(NOW - timedelta(hours=1), NOW)]


def test_startup_backfill_fills_coverage_holes_and_refreshes_recent_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = [(NOW - timedelta(minutes=30), NOW - timedelta(minutes=28))]

    class CoverageStore:
        def __init__(self) -> None:
            self.calls: list[tuple[datetime, datetime]] = []

        def missing_ranges(self, *, from_, to):
            self.calls.append((from_, to))
            return missing

    class Synchronizer:
        def __init__(self) -> None:
            self.calls: list[tuple[datetime, datetime]] = []

        def refresh_range(self, *, from_, to):
            self.calls.append((from_, to))

    heartbeats: list[str] = []
    monkeypatch.setattr(rollup_cli, "mark_worker_heartbeat", heartbeats.append)
    store = CoverageStore()
    synchronizer = Synchronizer()

    rollup_cli._backfill(
        synchronizer,
        store,
        hours=1,
        overlap_minutes=2,
        now=NOW + timedelta(seconds=30),
    )

    expected_start = (NOW - timedelta(hours=1)).replace(second=0, microsecond=0)
    expected_end = NOW.replace(second=0, microsecond=0) + timedelta(minutes=1)
    assert store.calls == [(expected_start, expected_end)]
    assert synchronizer.calls == [
        missing[0],
        (expected_end - timedelta(minutes=2), expected_end),
    ]
    assert heartbeats == ["dashboard-rollup-worker", "dashboard-rollup-worker"]


def test_explicit_backfill_rebuilds_the_full_requested_range(monkeypatch: pytest.MonkeyPatch) -> None:
    class CoverageStore:
        def missing_ranges(self, **_kwargs):
            raise AssertionError("forced backfill must not rely on existing coverage")

    class Synchronizer:
        def __init__(self) -> None:
            self.calls: list[tuple[datetime, datetime]] = []

        def refresh_range(self, *, from_, to):
            self.calls.append((from_, to))

    monkeypatch.setattr(rollup_cli, "mark_worker_heartbeat", lambda _worker: None)
    synchronizer = Synchronizer()

    rollup_cli._backfill(
        synchronizer,
        CoverageStore(),
        hours=1,
        overlap_minutes=2,
        chunk_hours=6,
        force_full=True,
        now=NOW + timedelta(seconds=30),
    )

    assert synchronizer.calls == [
        (
            (NOW - timedelta(hours=1)).replace(second=0, microsecond=0),
            NOW.replace(second=0, microsecond=0) + timedelta(minutes=1),
        )
    ]


def test_periodic_reconciliation_rebuilds_covered_buckets_instead_of_trusting_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Synchronizer:
        def __init__(self) -> None:
            self.calls: list[tuple[datetime, datetime]] = []

        def refresh_range(self, *, from_, to):
            self.calls.append((from_, to))

    class Worker:
        def __init__(self) -> None:
            self.flushes = 0

        def run_once(self, _timeout):
            return False

        def flush(self):
            self.flushes += 1

    monkeypatch.setattr(rollup_cli, "mark_worker_heartbeat", lambda _worker: None)
    synchronizer = Synchronizer()
    worker = Worker()

    last_attempt = rollup_cli._reconcile_if_due(
        synchronizer,
        worker,
        last_attempt_at=100,
        interval_seconds=300,
        hours=1,
        chunk_hours=2,
        max_pending=1,
        clock=lambda: 400,
        now=NOW,
    )

    assert last_attempt == 400
    assert synchronizer.calls == [
        (NOW - timedelta(hours=1), NOW + timedelta(minutes=1)),
    ]
    assert worker.flushes == 1


def test_backfill_is_chunked_and_services_stream_between_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    class Synchronizer:
        def __init__(self) -> None:
            self.calls: list[tuple[datetime, datetime]] = []

        def refresh_range(self, *, from_, to):
            self.calls.append((from_, to))

    turns: list[int] = []
    monkeypatch.setattr(rollup_cli, "mark_worker_heartbeat", lambda _worker: None)
    synchronizer = Synchronizer()

    rollup_cli._backfill(
        synchronizer,
        SimpleNamespace(),
        hours=3,
        overlap_minutes=2,
        chunk_hours=1,
        force_full=True,
        now=NOW,
        after_chunk=lambda: turns.append(len(synchronizer.calls)),
    )

    assert [end - start for start, end in synchronizer.calls] == [
        timedelta(hours=1),
        timedelta(hours=1),
        timedelta(hours=1),
        timedelta(minutes=1),
    ]
    assert turns == [1, 2, 3, 4]


def test_clickhouse_rollup_query_deduplicates_event_ids_and_caps_dimension_candidates() -> None:
    class Client:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def query(self, query: str, parameters=None):
            self.queries.append(query)
            return SimpleNamespace(result_rows=[])

    client = Client()
    EventRepository(client).dashboard_rollup_rows(from_=NOW, to=NOW + timedelta(minutes=1))

    assert len(client.queries) == 2
    assert all("uniqExact(event_id)" in query for query in client.queries)
    assert f"INTERVAL {DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS} SECOND" in client.queries[1]
    assert "LIMIT 50" in client.queries[1]
    assert "BY endpoint_id, bucket_start_at, dimension_name" in client.queries[1]
