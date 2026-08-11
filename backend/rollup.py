import json
import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from typing import Any, Protocol

from .failure import FailureSink
from .kafka import ConsumedMessage, ConsumerPort
from .storage.clickhouse import DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS

LOGGER = logging.getLogger(__name__)
MINUTE = timedelta(minutes=1)
DIRTY_QUERY_WINDOW = timedelta(hours=1)


class RollupEventSource(Protocol):
    def dashboard_rollup_rows(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_ids: list[int] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...


class RollupStore(Protocol):
    def replace_range(
        self,
        *,
        from_: datetime,
        to: datetime,
        activity_rows: list[dict[str, Any]],
        dimension_rows: list[dict[str, Any]],
        refreshed_at: datetime,
        endpoint_ids: list[int] | None = None,
    ) -> None: ...

    def replace_buckets(
        self,
        *,
        bucket_keys: Iterable[tuple[int, datetime]],
        dimension_bucket_keys: Iterable[tuple[int, datetime]],
        activity_rows: list[dict[str, Any]],
        dimension_rows: list[dict[str, Any]],
        refreshed_at: datetime,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RollupRefreshResult:
    bucket_count: int
    activity_row_count: int
    dimension_row_count: int
    refreshed_at: datetime
    skipped_bucket_count: int = 0


class InvalidRollupMessageError(ValueError):
    pass


class DashboardRollupSynchronizer:
    def __init__(
        self,
        *,
        events: RollupEventSource,
        store: RollupStore,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.events = events
        self.store = store
        self.now = now

    def refresh_range(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_ids: list[int] | None = None,
    ) -> RollupRefreshResult:
        from_ = _utc(from_)
        to = _utc(to)
        if from_ >= to:
            raise ValueError("rollup range must not be empty")
        if from_.second or from_.microsecond or to.second or to.microsecond:
            raise ValueError("rollup refresh range must use minute boundaries")
        bucket_dates = _bucket_dates_for_range(from_, to)
        activity_row_count = 0
        dimension_row_count = 0
        refreshed_keys: set[tuple[int, datetime]] = set()
        refreshed_at = self.now()
        with _writer_guard(self.store, bucket_dates=bucket_dates):
            frozen_dates = _frozen_bucket_dates(self.store, bucket_dates)
            refreshable_segments = _refreshable_range_segments(from_, to, frozen_dates)
            for segment_start, segment_end in refreshable_segments:
                activity_rows, dimension_rows = self.events.dashboard_rollup_rows(
                    from_=segment_start,
                    to=segment_end,
                    endpoint_ids=endpoint_ids,
                )
                refreshed_at = self.now()
                self.store.replace_range(
                    from_=segment_start,
                    to=segment_end,
                    activity_rows=activity_rows,
                    dimension_rows=dimension_rows,
                    refreshed_at=refreshed_at,
                    endpoint_ids=endpoint_ids,
                )
                activity_row_count += len(activity_rows)
                dimension_row_count += len(dimension_rows)
                refreshed_keys.update(_row_key(row) for row in activity_rows)
        skipped_bucket_count = _range_minute_count(from_, to) - sum(
            _range_minute_count(segment_start, segment_end)
            for segment_start, segment_end in refreshable_segments
        )
        if skipped_bucket_count:
            LOGGER.info(
                "dashboard rollup preserved frozen source buckets=%s from=%s to=%s",
                skipped_bucket_count,
                from_.isoformat(),
                to.isoformat(),
            )
        return RollupRefreshResult(
            len(refreshed_keys),
            activity_row_count,
            dimension_row_count,
            refreshed_at,
            skipped_bucket_count,
        )

    def refresh_buckets(self, bucket_keys: Iterable[tuple[int, datetime]]) -> RollupRefreshResult:
        normalized_keys = {(int(endpoint_id), _minute_bucket(bucket)) for endpoint_id, bucket in bucket_keys}
        if not normalized_keys:
            refreshed_at = self.now()
            return RollupRefreshResult(0, 0, 0, refreshed_at)

        bucket_dates = {bucket.date() for _endpoint_id, bucket in normalized_keys}
        with _writer_guard(self.store, bucket_dates=bucket_dates):
            frozen_dates = _frozen_bucket_dates(self.store, bucket_dates)
            refreshable_keys = {
                (endpoint_id, bucket)
                for endpoint_id, bucket in normalized_keys
                if bucket.date() not in frozen_dates
            }
            if not refreshable_keys:
                refreshed_at = self.now()
                return RollupRefreshResult(0, 0, 0, refreshed_at, len(normalized_keys))

            activity_rows: list[dict[str, Any]] = []
            dimension_rows: list[dict[str, Any]] = []
            by_query_window: dict[datetime, set[tuple[int, datetime]]] = {}
            for key in refreshable_keys:
                by_query_window.setdefault(_query_window(key[1]), set()).add(key)
            for window_keys in by_query_window.values():
                buckets = [bucket for _endpoint_id, bucket in window_keys]
                activity, dimensions = self.events.dashboard_rollup_rows(
                    from_=min(buckets),
                    to=max(buckets) + MINUTE,
                    endpoint_ids=sorted({endpoint_id for endpoint_id, _bucket in window_keys}),
                )
                activity_rows.extend(activity)
                dimension_rows.extend(dimensions)

            refreshed_at = self.now()
            filtered_activity_rows = [row for row in activity_rows if _row_key(row) in refreshable_keys]
            dimension_bucket_keys = {
                (endpoint_id, _dimension_bucket(bucket))
                for endpoint_id, bucket in refreshable_keys
            }
            filtered_dimension_rows = [
                row for row in dimension_rows if _dimension_row_key(row) in dimension_bucket_keys
            ]
            self.store.replace_buckets(
                bucket_keys=refreshable_keys,
                dimension_bucket_keys=dimension_bucket_keys,
                activity_rows=filtered_activity_rows,
                dimension_rows=filtered_dimension_rows,
                refreshed_at=refreshed_at,
            )
        return RollupRefreshResult(
            len(refreshable_keys),
            len(filtered_activity_rows),
            len(filtered_dimension_rows),
            refreshed_at,
            len(normalized_keys) - len(refreshable_keys),
        )


class DashboardRollupWorker:
    consumer_name = "dashboard-rollup-worker"

    def __init__(
        self,
        *,
        consumer: ConsumerPort,
        synchronizer: DashboardRollupSynchronizer,
        flush_interval_seconds: float = 5.0,
        max_dirty_buckets: int = 250,
        failure_sink: FailureSink | None = None,
        clock: Callable[[], float] = monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if flush_interval_seconds <= 0:
            raise ValueError("flush interval must be positive")
        if max_dirty_buckets < 1:
            raise ValueError("max dirty buckets must be positive")
        self.consumer = consumer
        self.synchronizer = synchronizer
        self.flush_interval_seconds = flush_interval_seconds
        self.max_dirty_buckets = max_dirty_buckets
        self.failure_sink = failure_sink
        self.clock = clock
        self.now = now
        self.dirty_buckets: set[tuple[int, datetime]] = set()
        self.pending_offsets: dict[tuple[str, int], ConsumedMessage] = {}
        self.last_flushed_at = clock()

    def run_once(self, timeout: float = 1.0) -> bool:
        message = self.consumer.consume_one(timeout)
        if message is not None:
            try:
                endpoint_id, bucket_start = _rollup_identity(message)
            except InvalidRollupMessageError as error:
                # Committing the poison offset before earlier valid messages in the
                # same partition would skip their projection on a crash.
                self.flush()
                self._quarantine_invalid_message(message, error)
            else:
                self.dirty_buckets.add((endpoint_id, bucket_start))
                partition_key = (message.topic, message.partition)
                previous = self.pending_offsets.get(partition_key)
                if previous is None or message.offset > previous.offset:
                    self.pending_offsets[partition_key] = message
        should_flush = bool(self.dirty_buckets) and (
            len(self.dirty_buckets) >= self.max_dirty_buckets
            or self.clock() - self.last_flushed_at >= self.flush_interval_seconds
        )
        if should_flush:
            self.flush()
        return message is not None

    def flush(self) -> RollupRefreshResult | None:
        if not self.dirty_buckets:
            return None
        result = self.synchronizer.refresh_buckets(self.dirty_buckets)
        ordered_messages = sorted(
            self.pending_offsets.values(),
            key=lambda item: (item.topic, item.partition, item.offset),
        )
        for message in ordered_messages:
            self.consumer.commit(message)
        LOGGER.info(
            "dashboard rollup refreshed buckets=%s skipped=%s activity_rows=%s dimension_rows=%s",
            result.bucket_count,
            result.skipped_bucket_count,
            result.activity_row_count,
            result.dimension_row_count,
        )
        self.dirty_buckets.clear()
        self.pending_offsets.clear()
        self.last_flushed_at = self.clock()
        return result

    def _quarantine_invalid_message(
        self,
        message: ConsumedMessage,
        error: InvalidRollupMessageError,
    ) -> None:
        if self.failure_sink is None:
            raise error
        try:
            self.failure_sink.record(
                message,
                consumer_name=self.consumer_name,
                failure_stage="DASHBOARD_ROLLUP",
                failure_code="INVALID_MESSAGE",
                error_message=str(error),
                retryable=False,
                retry_count=0,
                failed_at=self.now(),
            )
        except Exception:
            LOGGER.exception(
                "rollup failure persistence failed; rewinding topic=%s partition=%s offset=%s",
                message.topic,
                message.partition,
                message.offset,
            )
            rewind = getattr(self.consumer, "rewind", None)
            if callable(rewind):
                rewind(message)
            raise
        self.consumer.commit(message)
        LOGGER.warning(
            "rollup poison message quarantined topic=%s partition=%s offset=%s",
            message.topic,
            message.partition,
            message.offset,
        )


def _rollup_identity(message: ConsumedMessage) -> tuple[int, datetime]:
    try:
        payload = json.loads(message.value)
        event = payload["event"]
        endpoint_id = int(event["endpoint_id"])
        occurred_at = datetime.fromisoformat(str(event["occurred_at"]).replace("Z", "+00:00"))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise InvalidRollupMessageError("validated Event message cannot be used for rollup") from error
    return endpoint_id, _minute_bucket(occurred_at)


def _minute_bucket(value: datetime) -> datetime:
    return _utc(value).replace(second=0, microsecond=0)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _row_key(row: dict[str, Any]) -> tuple[int, datetime]:
    return int(row["endpoint_id"]), _minute_bucket(row["bucket_start_at"])


def _dimension_bucket(value: datetime) -> datetime:
    value = _utc(value)
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(
        epoch - (epoch % DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS),
        UTC,
    )


def _dimension_row_key(row: dict[str, Any]) -> tuple[int, datetime]:
    return int(row["endpoint_id"]), _dimension_bucket(row["bucket_start_at"])


def _contiguous_segments(values: Iterable[datetime]) -> list[tuple[datetime, datetime]]:
    ordered = sorted({_minute_bucket(value) for value in values})
    if not ordered:
        return []
    segments: list[tuple[datetime, datetime]] = []
    start = previous = ordered[0]
    for current in ordered[1:]:
        if current - previous > MINUTE:
            segments.append((start, previous))
            start = current
        previous = current
    segments.append((start, previous))
    return segments


def _query_window(value: datetime) -> datetime:
    bucket = _minute_bucket(value)
    elapsed = int(bucket.timestamp()) % int(DIRTY_QUERY_WINDOW.total_seconds())
    return bucket - timedelta(seconds=elapsed)


def _bucket_dates_for_range(from_: datetime, to: datetime) -> set[date]:
    last = (to - timedelta(microseconds=1)).date()
    current = from_.date()
    result: set[date] = set()
    while current <= last:
        result.add(current)
        current += timedelta(days=1)
    return result


def _frozen_bucket_dates(store: RollupStore, bucket_dates: Iterable[date]) -> set[date]:
    lookup = getattr(store, "frozen_bucket_dates", None)
    if not callable(lookup):
        return set()
    return set(lookup(bucket_dates=set(bucket_dates)))


def _refreshable_range_segments(
    from_: datetime,
    to: datetime,
    frozen_dates: set[date],
) -> list[tuple[datetime, datetime]]:
    segments: list[tuple[datetime, datetime]] = []
    cursor = from_
    current_start: datetime | None = None
    while cursor < to:
        next_day = cursor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        segment_end = min(next_day, to)
        if cursor.date() in frozen_dates:
            if current_start is not None:
                segments.append((current_start, cursor))
                current_start = None
        elif current_start is None:
            current_start = cursor
        cursor = segment_end
    if current_start is not None:
        segments.append((current_start, to))
    return segments


def _range_minute_count(from_: datetime, to: datetime) -> int:
    return int((to - from_).total_seconds() // 60)


def _writer_guard(
    store: RollupStore,
    *,
    bucket_dates: Iterable[date],
) -> AbstractContextManager[None]:
    guard = getattr(store, "writer_guard", None)
    return guard(bucket_dates=set(bucket_dates)) if callable(guard) else nullcontext()
