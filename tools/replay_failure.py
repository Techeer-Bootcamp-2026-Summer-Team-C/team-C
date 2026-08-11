import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from backend.failure import FailureSink
from backend.runtime import RuntimeServices
from backend.settings import get_settings
from backend.storage.clickhouse import FailureRepository
from backend.workers import canonical_json


class FailureNotFoundError(Exception):
    pass


class FailureReplayInProgressError(Exception):
    pass


def replay_failure(failure_id: UUID, runtime: RuntimeServices, *, now: datetime) -> None:
    with _failure_replay_guard(runtime, failure_id):
        _replay_failure_unlocked(failure_id, runtime, now=now)


def _replay_failure_unlocked(failure_id: UUID, runtime: RuntimeServices, *, now: datetime) -> None:
    repository = FailureRepository(runtime.clickhouse)
    failure = repository.latest(failure_id)
    if failure is None:
        raise FailureNotFoundError(str(failure_id))
    sink = FailureSink(
        s3_client=runtime.s3,
        bucket=runtime.settings.s3_bucket,
        repository=repository,
    )
    try:
        envelope = sink.load_verified(failure, now=now)
        source_message = envelope["message"]
        raw_message = (
            source_message["raw"]
            if envelope["sourceTopic"] == runtime.settings.kafka_validated_topic
            else source_message
        )
        acknowledged = runtime.producer.publish(
            runtime.settings.kafka_raw_topic,
            key=str(raw_message["endpointId"]),
            value=canonical_json(raw_message),
            headers=[("replay_failure_id", str(failure_id).encode())],
        )
        if not acknowledged:
            raise RuntimeError("Kafka broker did not acknowledge replay")
    except Exception as error:
        repository.append_replay_result(
            failure,
            status="REPROCESS_FAILED",
            outcome=str(error),
            replayed_at=now,
        )
        raise
    repository.append_replay_result(
        failure,
        status="REPLAY_PUBLISHED",
        outcome="telemetry.raw broker acknowledged",
        replayed_at=now,
    )


@contextmanager
def _failure_replay_guard(runtime: RuntimeServices, failure_id: UUID) -> Iterator[None]:
    with runtime.postgres() as connection:
        acquired = connection.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s), hashtext(%s))",
            ("failure-replay-v1", str(failure_id)),
        ).fetchone()
        if acquired is None or not bool(acquired[0]):
            raise FailureReplayInProgressError(str(failure_id))
        try:
            yield
        finally:
            connection.execute(
                "SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))",
                ("failure-replay-v1", str(failure_id)),
            ).fetchone()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay one durable EDR failure to telemetry.raw.")
    parser.add_argument("--failure-id", required=True, type=UUID)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = RuntimeServices(get_settings(), clickhouse_role="worker")
        replay_failure(args.failure_id, runtime, now=datetime.now(UTC))
    except FailureNotFoundError:
        print(f"failure not found: {args.failure_id}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"replay failed: {error}", file=sys.stderr)
        return 1
    print(f"replay published: {args.failure_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
