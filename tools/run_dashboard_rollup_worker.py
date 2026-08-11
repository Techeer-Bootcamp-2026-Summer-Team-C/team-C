import argparse
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import monotonic

from backend.failure import FailureSink
from backend.kafka import KafkaConsumer
from backend.rollup import DashboardRollupSynchronizer, DashboardRollupWorker
from backend.runtime import RuntimeServices
from backend.settings import get_settings
from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.storage.rollup import DashboardEventRollupRepository
from backend.worker_health import mark_worker_heartbeat

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Roll up ClickHouse Event metrics into PostgreSQL and follow telemetry.validated changes."
    )
    parser.add_argument("--once", action="store_true", help="Consume at most one message, flush it, and exit.")
    parser.add_argument("--backfill-only", action="store_true", help="Refresh the configured recent range and exit.")
    parser.add_argument("--backfill-hours", type=int, help="Override the configured initial backfill range.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = RuntimeServices(get_settings(), clickhouse_role="worker")
    consumer = KafkaConsumer(
        runtime.settings.kafka_bootstrap_servers,
        group_id=runtime.settings.dashboard_rollup_consumer_group,
        topic=runtime.settings.kafka_validated_topic,
        allowed_topics=runtime.settings.kafka_topics,
    )
    try:
        with runtime.postgres() as connection:
            # This process owns a long-lived connection. Autocommit keeps read-only
            # coverage checks from opening an outer transaction that would trap all
            # later rollup writes until the worker exits.
            connection.autocommit = True
            store = DashboardEventRollupRepository(connection)
            synchronizer = DashboardRollupSynchronizer(
                events=EventRepository(runtime.clickhouse),
                store=store,
            )
            worker = DashboardRollupWorker(
                consumer=consumer,
                synchronizer=synchronizer,
                flush_interval_seconds=runtime.settings.dashboard_rollup_flush_seconds,
                max_dirty_buckets=runtime.settings.dashboard_rollup_max_dirty_buckets,
                failure_sink=FailureSink(
                    s3_client=runtime.s3,
                    bucket=runtime.settings.s3_bucket,
                    repository=FailureRepository(runtime.clickhouse),
                ),
            )
            _backfill(
                synchronizer,
                store,
                hours=(
                    args.backfill_hours
                    if args.backfill_hours is not None
                    else runtime.settings.dashboard_rollup_backfill_hours
                ),
                overlap_minutes=runtime.settings.dashboard_rollup_overlap_minutes,
                chunk_hours=runtime.settings.dashboard_rollup_backfill_chunk_hours,
                force_full=args.backfill_only or args.backfill_hours is not None,
                after_chunk=(
                    None
                    if args.backfill_only or args.once
                    else lambda: _drain_pending(worker, limit=runtime.settings.dashboard_rollup_max_dirty_buckets)
                ),
            )
            if args.backfill_only:
                return 0
            if args.once:
                consumed = worker.run_once(10)
                worker.flush()
                return 0 if consumed else 1
            last_reconciliation_attempt = monotonic()
            while True:
                worker.run_once(1)
                mark_worker_heartbeat("dashboard-rollup-worker")
                last_reconciliation_attempt = _reconcile_if_due(
                    synchronizer,
                    worker,
                    last_attempt_at=last_reconciliation_attempt,
                    interval_seconds=runtime.settings.dashboard_rollup_reconcile_interval_seconds,
                    hours=runtime.settings.dashboard_rollup_reconcile_hours,
                    chunk_hours=runtime.settings.dashboard_rollup_backfill_chunk_hours,
                    max_pending=runtime.settings.dashboard_rollup_max_dirty_buckets,
                )
    except KeyboardInterrupt:
        return 0
    finally:
        consumer.close()


def _backfill(
    synchronizer: DashboardRollupSynchronizer,
    store: DashboardEventRollupRepository | None,
    *,
    hours: int,
    overlap_minutes: int,
    chunk_hours: int = 1,
    force_full: bool = False,
    now: datetime | None = None,
    after_chunk: Callable[[], None] | None = None,
) -> None:
    if hours < 1:
        raise ValueError("backfill hours must be positive")
    if overlap_minutes < 1:
        raise ValueError("backfill overlap must be positive")
    if chunk_hours < 1:
        raise ValueError("backfill chunk hours must be positive")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    earliest = (current - timedelta(hours=hours)).replace(second=0, microsecond=0)
    end = current.replace(second=0, microsecond=0) + timedelta(minutes=1)
    if force_full:
        ranges = [(earliest, end)]
    else:
        if store is None:
            raise ValueError("coverage store is required for incremental backfill")
        ranges = store.missing_ranges(from_=earliest, to=end)
        ranges.append((max(earliest, end - timedelta(minutes=overlap_minutes)), end))
    chunk = timedelta(hours=chunk_hours)
    for range_start, range_end in _merge_ranges(ranges):
        cursor = range_start
        while cursor < range_end:
            chunk_end = min(cursor + chunk, range_end)
            synchronizer.refresh_range(from_=cursor, to=chunk_end)
            mark_worker_heartbeat("dashboard-rollup-worker")
            if after_chunk is not None:
                after_chunk()
            cursor = chunk_end


def _drain_pending(worker: DashboardRollupWorker, *, limit: int) -> None:
    """Give the streaming consumer a bounded turn between backfill chunks."""
    for _index in range(limit):
        if not worker.run_once(0):
            break
    worker.flush()
    mark_worker_heartbeat("dashboard-rollup-worker")


def _reconcile_if_due(
    synchronizer: DashboardRollupSynchronizer,
    worker: DashboardRollupWorker,
    *,
    last_attempt_at: float,
    interval_seconds: int,
    hours: int,
    chunk_hours: int,
    max_pending: int,
    clock: Callable[[], float] = monotonic,
    now: datetime | None = None,
) -> float:
    attempted_at = clock()
    if attempted_at - last_attempt_at < interval_seconds:
        return last_attempt_at
    try:
        _backfill(
            synchronizer,
            store=None,
            hours=hours,
            overlap_minutes=1,
            chunk_hours=chunk_hours,
            force_full=True,
            now=now,
            after_chunk=lambda: _drain_pending(worker, limit=max_pending),
        )
    except Exception:
        # Streaming dirty-bucket processing remains available even if the safety
        # reconciliation pass fails. The next scheduled pass retries the range.
        LOGGER.exception("periodic dashboard rollup reconciliation failed")
    return attempted_at


def _merge_ranges(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    ordered = sorted((start, end) for start, end in ranges if start < end)
    if not ordered:
        return []
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


if __name__ == "__main__":
    raise SystemExit(main())
