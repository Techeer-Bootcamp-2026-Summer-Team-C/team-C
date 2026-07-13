import argparse

from backend.failure import FailureSink
from backend.kafka import RAW_TOPIC, KafkaConsumer
from backend.runtime import RuntimeServices
from backend.settings import get_settings
from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.storage.postgres import IngestMetadataRepository
from backend.workers import EventStorageWorker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the telemetry.raw Event Storage Worker.")
    parser.add_argument("--once", action="store_true", help="Consume at most one message and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = RuntimeServices(get_settings())
    consumer = KafkaConsumer(
        runtime.settings.kafka_bootstrap_servers,
        group_id="edr-event-storage-v1",
        topic=RAW_TOPIC,
    )
    try:
        with runtime.postgres() as connection:
            worker = EventStorageWorker(
                consumer=consumer,
                producer=runtime.producer,
                events=EventRepository(runtime.clickhouse),
                metadata=IngestMetadataRepository(connection),
                failure_sink=FailureSink(
                    s3_client=runtime.s3,
                    bucket=runtime.settings.s3_bucket,
                    repository=FailureRepository(runtime.clickhouse),
                ),
            )
            if args.once:
                return 0 if worker.run_once(10) else 1
            while True:
                worker.run_once(1)
    except KeyboardInterrupt:
        return 0
    finally:
        consumer.close()


if __name__ == "__main__":
    raise SystemExit(main())
