from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from psycopg.rows import dict_row

from .clickhouse import (
    DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS,
    DASHBOARD_TOP_LIMIT,
    DashboardEventAggregate,
)

ROLLUP_NAME = "dashboard-events-v1"
DIMENSION_NAMES = (
    "top_processes",
    "top_remote_ips",
    "top_domains",
    "top_file_hashes",
    "top_dns_queries",
    "top_l7_protocols",
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _expanded_bucket_bounds(
    from_: datetime,
    to: datetime,
    *,
    bucket_seconds: int,
) -> tuple[datetime, datetime]:
    from_ = _utc(from_)
    to = _utc(to)
    start_epoch = int(from_.timestamp())
    end_epoch = int(to.timestamp())
    expanded_start = start_epoch - (start_epoch % bucket_seconds)
    expanded_end = (
        end_epoch
        if end_epoch % bucket_seconds == 0
        else end_epoch + bucket_seconds - (end_epoch % bucket_seconds)
    )
    return datetime.fromtimestamp(expanded_start, UTC), datetime.fromtimestamp(expanded_end, UTC)


class DashboardEventRollupRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @contextmanager
    def writer_guard(self, *, bucket_dates: Iterable[date] = ()) -> Iterator[None]:
        """Serialize one refresh and keep archive deletion outside its source snapshot."""
        with self.connection.transaction():
            self._lock()
            for bucket_date in sorted(set(bucket_dates)):
                self.connection.execute(
                    "SELECT pg_advisory_xact_lock_shared(hashtext(%s))",
                    (_archive_lock_name(bucket_date),),
                )
            yield

    def frozen_bucket_dates(self, *, bucket_dates: Iterable[date]) -> set[date]:
        """Return ClickHouse dates that have been frozen for partition deletion.

        A frozen date is no longer a complete ClickHouse source. Refreshing it from
        ClickHouse alone would replace durable PostgreSQL rollups with empty or
        partial results after the partition has been dropped.
        """
        normalized = sorted(set(bucket_dates))
        if not normalized:
            return set()
        bucket_starts = [datetime.combine(bucket_date, time.min, tzinfo=UTC) for bucket_date in normalized]
        rows = self.connection.execute(
            """
            SELECT DISTINCT bucket_start_at
            FROM ingest_metadata
            WHERE bucket_start_at = ANY(%s::timestamptz[])
              AND storage_backend = 'CLICKHOUSE'
              AND storage_class = 'HOT'
              AND (is_delete = TRUE OR partition_deleted_at IS NOT NULL)
            """,
            (bucket_starts,),
        ).fetchall()
        return {_utc(row[0]).date() for row in rows}

    def replace_range(
        self,
        *,
        from_: datetime,
        to: datetime,
        activity_rows: Sequence[dict[str, Any]],
        dimension_rows: Sequence[dict[str, Any]],
        refreshed_at: datetime,
        endpoint_ids: Sequence[int] | None = None,
    ) -> None:
        from_ = _utc(from_)
        to = _utc(to)
        if from_ >= to:
            raise ValueError("rollup range must not be empty")
        if from_.second or from_.microsecond or to.second or to.microsecond:
            raise ValueError("rollup replacement range must use minute boundaries")
        with self.connection.transaction():
            self._lock()
            parameters = (
                from_,
                to,
                list(endpoint_ids) if endpoint_ids is not None else None,
                list(endpoint_ids) if endpoint_ids is not None else None,
            )
            predicate = (
                "bucket_start_at >= %s AND bucket_start_at < %s "
                "AND (%s::bigint[] IS NULL OR endpoint_id = ANY(%s::bigint[]))"
            )
            self.connection.execute(f"DELETE FROM dashboard_event_rollups WHERE {predicate}", parameters)
            dimension_from, dimension_to = _expanded_bucket_bounds(
                from_,
                to,
                bucket_seconds=DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS,
            )
            dimension_parameters = (
                dimension_from,
                dimension_to,
                list(endpoint_ids) if endpoint_ids is not None else None,
                list(endpoint_ids) if endpoint_ids is not None else None,
                DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS,
            )
            self.connection.execute(
                """
                DELETE FROM dashboard_event_dimension_rollups
                WHERE bucket_start_at >= %s AND bucket_start_at < %s
                  AND (%s::bigint[] IS NULL OR endpoint_id = ANY(%s::bigint[]))
                  AND bucket_width_seconds = %s
                """,
                dimension_parameters,
            )
            self._insert_activity(activity_rows, refreshed_at=refreshed_at)
            self._insert_dimensions(dimension_rows, refreshed_at=refreshed_at)
            self._record_state(
                covered_from=from_,
                covered_through=to,
                source_max_ingested_at=_max_source_ingested_at(activity_rows),
                refreshed_at=refreshed_at,
            )
            if endpoint_ids is None:
                self._record_coverage(from_=from_, to=to, refreshed_at=refreshed_at)

    def replace_buckets(
        self,
        *,
        bucket_keys: Iterable[tuple[int, datetime]],
        dimension_bucket_keys: Iterable[tuple[int, datetime]],
        activity_rows: Sequence[dict[str, Any]],
        dimension_rows: Sequence[dict[str, Any]],
        refreshed_at: datetime,
    ) -> None:
        normalized_keys = sorted({(int(endpoint_id), _utc(bucket_start)) for endpoint_id, bucket_start in bucket_keys})
        if not normalized_keys:
            return
        normalized_dimension_keys = sorted(
            {
                (int(endpoint_id), _utc(bucket_start))
                for endpoint_id, bucket_start in dimension_bucket_keys
            }
        )
        with self.connection.transaction():
            self._lock()
            endpoint_ids = [endpoint_id for endpoint_id, _bucket_start in normalized_keys]
            bucket_starts = [bucket_start for _endpoint_id, bucket_start in normalized_keys]
            delete_parameters = (endpoint_ids, bucket_starts)
            self.connection.execute(
                """
                DELETE FROM dashboard_event_rollups AS rollup
                USING unnest(%s::bigint[], %s::timestamptz[]) AS target(endpoint_id, bucket_start_at)
                WHERE rollup.endpoint_id = target.endpoint_id
                  AND rollup.bucket_start_at = target.bucket_start_at
                """,
                delete_parameters,
            )
            if normalized_dimension_keys:
                dimension_endpoint_ids = [endpoint_id for endpoint_id, _bucket in normalized_dimension_keys]
                dimension_bucket_starts = [bucket for _endpoint_id, bucket in normalized_dimension_keys]
                self.connection.execute(
                    """
                    DELETE FROM dashboard_event_dimension_rollups AS rollup
                    USING unnest(%s::bigint[], %s::timestamptz[])
                        AS target(endpoint_id, bucket_start_at)
                    WHERE rollup.endpoint_id = target.endpoint_id
                      AND rollup.bucket_start_at = target.bucket_start_at
                      AND rollup.bucket_width_seconds = %s
                    """,
                    (
                        dimension_endpoint_ids,
                        dimension_bucket_starts,
                        DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS,
                    ),
                )
            self._insert_activity(activity_rows, refreshed_at=refreshed_at)
            self._insert_dimensions(dimension_rows, refreshed_at=refreshed_at)
            self._record_state(
                covered_from=min(bucket for _endpoint, bucket in normalized_keys),
                covered_through=max(bucket for _endpoint, bucket in normalized_keys) + timedelta(minutes=1),
                source_max_ingested_at=_max_source_ingested_at(activity_rows),
                refreshed_at=refreshed_at,
            )

    def dashboard_summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        interval_seconds: int,
        endpoint_id: int | None = None,
    ) -> DashboardEventAggregate:
        from_ = _utc(from_)
        to = _utc(to)
        if interval_seconds not in {60, 300, 3600, 86400}:
            raise ValueError("unsupported dashboard interval")
        aggregate = DashboardEventAggregate()
        parameters = (interval_seconds, from_, to, endpoint_id, endpoint_id)
        activity_rows = self.connection.execute(
            """
            SELECT
                event_type,
                date_bin(make_interval(secs => %s), bucket_start_at, TIMESTAMPTZ '1970-01-01 00:00:00+00')
                    AS grouped_bucket_start_at,
                SUM(event_count)::bigint AS event_count
            FROM dashboard_event_rollups
            WHERE bucket_start_at >= date_trunc('minute', %s::timestamptz)
              AND bucket_start_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s)
            GROUP BY event_type, grouped_bucket_start_at
            ORDER BY grouped_bucket_start_at, event_type
            """,
            parameters,
        ).fetchall()
        for event_type, bucket_start_at, count in activity_rows:
            rendered_count = int(count)
            aggregate.total_count += rendered_count
            aggregate.by_event_type[str(event_type)] += rendered_count
            aggregate.time_series[_utc(bucket_start_at)] += rendered_count

        dimension_rows = self.connection.execute(
            """
            WITH ranked AS (
                SELECT
                    dimension_name,
                    dimension_value,
                    SUM(event_count)::bigint AS event_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY dimension_name
                        ORDER BY SUM(event_count) DESC, dimension_value ASC
                    ) AS rank
                FROM dashboard_event_dimension_rollups
                WHERE bucket_start_at >= date_bin(
                          make_interval(secs => %s),
                          %s::timestamptz,
                          TIMESTAMPTZ '1970-01-01 00:00:00+00'
                      )
                  AND bucket_start_at < %s
                  AND (%s::bigint IS NULL OR endpoint_id = %s)
                  AND bucket_width_seconds = %s
                GROUP BY dimension_name, dimension_value
            )
            SELECT dimension_name, dimension_value, event_count
            FROM ranked
            WHERE rank <= %s
            ORDER BY dimension_name, rank
            """,
            (
                DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS,
                from_,
                to,
                endpoint_id,
                endpoint_id,
                DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS,
                DASHBOARD_TOP_LIMIT,
            ),
        ).fetchall()
        counters: dict[str, Counter[str]] = {
            name: getattr(aggregate, name)
            for name in DIMENSION_NAMES
        }
        for dimension_name, dimension_value, count in dimension_rows:
            counter = counters.get(str(dimension_name))
            if counter is not None:
                counter[str(dimension_value)] = int(count)
        return aggregate

    def missing_ranges(self, *, from_: datetime, to: datetime) -> list[tuple[datetime, datetime]]:
        from_ = _utc(from_)
        to = _utc(to)
        if from_ >= to:
            return []
        required_from, required_through = _coverage_bounds(from_, to)
        rows = self.connection.execute(
            """
            SELECT candidate.bucket_start_at
            FROM generate_series(
                %s::timestamptz,
                %s::timestamptz - INTERVAL '1 minute',
                INTERVAL '1 minute'
            ) AS candidate(bucket_start_at)
            LEFT JOIN dashboard_rollup_coverage AS coverage
              ON coverage.rollup_name = %s
             AND coverage.bucket_start_at = candidate.bucket_start_at
            WHERE coverage.bucket_start_at IS NULL
            ORDER BY candidate.bucket_start_at
            """,
            (required_from, required_through, ROLLUP_NAME),
        ).fetchall()
        missing = [_utc(row[0]) for row in rows]
        if not missing:
            return []
        ranges: list[tuple[datetime, datetime]] = []
        start = previous = missing[0]
        for current in missing[1:]:
            if current - previous > timedelta(minutes=1):
                ranges.append((start, previous + timedelta(minutes=1)))
                start = current
            previous = current
        ranges.append((start, previous + timedelta(minutes=1)))
        return ranges

    def covers_range(self, *, from_: datetime, to: datetime) -> bool:
        from_ = _utc(from_)
        to = _utc(to)
        if from_ >= to:
            return True
        required_from, required_through = _coverage_bounds(from_, to)
        row = self.connection.execute(
            """
            SELECT count(*)
            FROM dashboard_rollup_coverage
            WHERE rollup_name = %s
              AND bucket_start_at >= %s
              AND bucket_start_at < %s
            """,
            (ROLLUP_NAME, required_from, required_through),
        ).fetchone()
        expected = int((required_through - required_from).total_seconds() // 60)
        return row is not None and int(row[0]) == expected

    def latest_ingested_at(self, *, endpoint_id: int | None = None) -> datetime | None:
        row = self.connection.execute(
            """
            SELECT max(source_max_ingested_at)
            FROM dashboard_event_rollups
            WHERE (%s::bigint IS NULL OR endpoint_id = %s)
            """,
            (endpoint_id, endpoint_id),
        ).fetchone()
        return _utc(row[0]) if row and row[0] is not None else None

    def state(self) -> dict[str, Any] | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM dashboard_rollup_state WHERE rollup_name = %s", (ROLLUP_NAME,))
            row = cursor.fetchone()
        return dict(row) if row is not None else None

    def _lock(self) -> None:
        self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (ROLLUP_NAME,))

    def _insert_activity(self, rows: Sequence[dict[str, Any]], *, refreshed_at: datetime) -> None:
        if not rows:
            return
        with self.connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO dashboard_event_rollups (
                    bucket_start_at, endpoint_id, event_type, event_count, source_max_ingested_at, refreshed_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (bucket_start_at, endpoint_id, event_type) DO UPDATE
                SET event_count = EXCLUDED.event_count,
                    source_max_ingested_at = EXCLUDED.source_max_ingested_at,
                    refreshed_at = EXCLUDED.refreshed_at
                """,
                [
                    (
                        _utc(row["bucket_start_at"]),
                        int(row["endpoint_id"]),
                        str(row["event_type"]),
                        int(row["event_count"]),
                        _optional_utc(row.get("source_max_ingested_at")),
                        refreshed_at,
                    )
                    for row in rows
                ],
            )

    def _insert_dimensions(self, rows: Sequence[dict[str, Any]], *, refreshed_at: datetime) -> None:
        if not rows:
            return
        with self.connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO dashboard_event_dimension_rollups (
                    bucket_start_at, endpoint_id, dimension_name, dimension_value,
                    bucket_width_seconds, event_count, refreshed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    bucket_start_at, endpoint_id, dimension_name, dimension_value, bucket_width_seconds
                ) DO UPDATE
                SET event_count = EXCLUDED.event_count,
                    refreshed_at = EXCLUDED.refreshed_at
                """,
                [
                    (
                        _utc(row["bucket_start_at"]),
                        int(row["endpoint_id"]),
                        str(row["dimension_name"]),
                        str(row["dimension_value"]),
                        DASHBOARD_ROLLUP_DIMENSION_BUCKET_SECONDS,
                        int(row["event_count"]),
                        refreshed_at,
                    )
                    for row in rows
                ],
            )

    def _record_state(
        self,
        *,
        covered_from: datetime,
        covered_through: datetime,
        source_max_ingested_at: datetime | None,
        refreshed_at: datetime,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO dashboard_rollup_state (
                rollup_name, covered_from, covered_through, source_max_ingested_at, refreshed_at
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (rollup_name) DO UPDATE
            SET covered_from = LEAST(dashboard_rollup_state.covered_from, EXCLUDED.covered_from),
                covered_through = GREATEST(dashboard_rollup_state.covered_through, EXCLUDED.covered_through),
                source_max_ingested_at = GREATEST(
                    dashboard_rollup_state.source_max_ingested_at,
                    EXCLUDED.source_max_ingested_at
                ),
                refreshed_at = EXCLUDED.refreshed_at
            """,
            (ROLLUP_NAME, covered_from, covered_through, source_max_ingested_at, refreshed_at),
        )

    def _record_coverage(self, *, from_: datetime, to: datetime, refreshed_at: datetime) -> None:
        self.connection.execute(
            """
            INSERT INTO dashboard_rollup_coverage (rollup_name, bucket_start_at, refreshed_at)
            SELECT %s, bucket_start_at, %s
            FROM generate_series(
                %s::timestamptz,
                %s::timestamptz - INTERVAL '1 minute',
                INTERVAL '1 minute'
            ) AS bucket(bucket_start_at)
            ON CONFLICT (rollup_name, bucket_start_at) DO UPDATE
            SET refreshed_at = EXCLUDED.refreshed_at
            """,
            (ROLLUP_NAME, refreshed_at, from_, to),
        )


def _optional_utc(value: Any) -> datetime | None:
    return _utc(value) if isinstance(value, datetime) else None


def _max_source_ingested_at(rows: Sequence[dict[str, Any]]) -> datetime | None:
    values = [
        _utc(value)
        for row in rows
        if isinstance((value := row.get("source_max_ingested_at")), datetime)
    ]
    return max(values, default=None)


def _coverage_bounds(from_: datetime, to: datetime) -> tuple[datetime, datetime]:
    required_from = from_.replace(second=0, microsecond=0)
    required_through = to.replace(second=0, microsecond=0)
    if required_through < to:
        required_through += timedelta(minutes=1)
    return required_from, required_through


def _archive_lock_name(bucket_date: date) -> str:
    return f"edr_events:{bucket_date.isoformat()}"
