import argparse

from backend.failure import FailureSink
from backend.kafka import KafkaConsumer
from backend.runtime import RuntimeServices
from backend.settings import get_settings
from backend.storage.clickhouse import EventRepository, FailureRepository
from backend.storage.postgres import IngestMetadataRepository
from backend.worker_health import mark_worker_heartbeat
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
        group_id=runtime.settings.event_storage_consumer_group,
        topic=runtime.settings.kafka_raw_topic,
        allowed_topics=runtime.settings.kafka_topics,
    )
    try:
        if args.once:
            with runtime.postgres() as connection:
                worker = _worker(runtime, consumer, connection)
                return 0 if worker.run_once(10) else 1
        while True:
            with runtime.postgres() as connection:
                worker = _worker(runtime, consumer, connection)
                while not worker.reset_requested:
                    worker.run_once(1)
                    mark_worker_heartbeat("event-storage-worker")
    except KeyboardInterrupt:
        return 0
    finally:
        consumer.close()


def _worker(runtime, consumer, connection) -> EventStorageWorker:
    return EventStorageWorker(
        consumer=consumer,
        producer=runtime.producer,
        events=EventRepository(runtime.clickhouse),
        metadata=IngestMetadataRepository(connection),
        failure_sink=FailureSink(
            s3_client=runtime.s3,
            bucket=runtime.settings.s3_bucket,
            repository=FailureRepository(runtime.clickhouse),
        ),
        validated_topic=runtime.settings.kafka_validated_topic,
    )


if __name__ == "__main__":
    raise SystemExit(main())
