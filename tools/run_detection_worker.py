import argparse
import time
from datetime import UTC, datetime

from backend.detection import DetectionEngine
from backend.failure import FailureSink
from backend.kafka import VALIDATED_TOPIC, KafkaConsumer
from backend.runtime import RuntimeServices
from backend.settings import get_settings
from backend.storage.clickhouse import FailureRepository
from backend.storage.postgres import AlertRepository, EndpointRepository, IncidentRepository
from backend.workers import DetectionWorker, LifecycleTasks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the telemetry.validated Detection Worker.")
    parser.add_argument("--once", action="store_true", help="Consume at most one message and run lifecycle once.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = RuntimeServices(get_settings())
    consumer = KafkaConsumer(
        runtime.settings.kafka_bootstrap_servers,
        group_id="edr-detection-v1",
        topic=VALIDATED_TOPIC,
    )
    try:
        with runtime.postgres() as connection:
            incidents = IncidentRepository(connection)
            worker = DetectionWorker(
                consumer=consumer,
                engine=DetectionEngine(runtime.rules),
                alerts=AlertRepository(connection),
                incidents=incidents,
                failure_sink=FailureSink(
                    s3_client=runtime.s3,
                    bucket=runtime.settings.s3_bucket,
                    repository=FailureRepository(runtime.clickhouse),
                ),
            )
            lifecycle = LifecycleTasks(EndpointRepository(connection), incidents)
            if args.once:
                consumed = worker.run_once(10)
                lifecycle.run_once(now=datetime.now(UTC))
                return 0 if consumed else 1
            next_endpoint_sweep = time.monotonic()
            next_incident_sweep = time.monotonic()
            while True:
                worker.run_once(1)
                monotonic_now = time.monotonic()
                utc_now = datetime.now(UTC)
                if monotonic_now >= next_endpoint_sweep:
                    lifecycle.mark_offline(now=utc_now)
                    next_endpoint_sweep = monotonic_now + 30
                if monotonic_now >= next_incident_sweep:
                    lifecycle.close_incidents(now=utc_now)
                    next_incident_sweep = monotonic_now + 60
    except KeyboardInterrupt:
        return 0
    finally:
        consumer.close()


if __name__ == "__main__":
    raise SystemExit(main())
