import argparse
import sys
from datetime import UTC, datetime
from uuid import UUID

from backend.failure import FailureSink
from backend.kafka import RAW_TOPIC
from backend.runtime import RuntimeServices
from backend.settings import get_settings
from backend.storage.clickhouse import FailureRepository
from backend.workers import canonical_json


class FailureNotFoundError(Exception):
    pass


def replay_failure(failure_id: UUID, runtime: RuntimeServices, *, now: datetime) -> None:
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
        raw_message = source_message["raw"] if envelope["sourceTopic"] == "telemetry.validated" else source_message
        acknowledged = runtime.producer.publish(
            RAW_TOPIC,
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
        status="REPROCESSED",
        outcome="telemetry.raw broker acknowledged",
        replayed_at=now,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay one durable EDR failure to telemetry.raw.")
    parser.add_argument("--failure-id", required=True, type=UUID)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = RuntimeServices(get_settings())
        replay_failure(args.failure_id, runtime, now=datetime.now(UTC))
    except FailureNotFoundError:
        print(f"failure not found: {args.failure_id}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"replay failed: {error}", file=sys.stderr)
        return 1
    print(f"replayed failure: {args.failure_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
