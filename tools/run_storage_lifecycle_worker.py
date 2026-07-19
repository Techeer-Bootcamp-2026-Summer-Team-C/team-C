import argparse
import logging
import time
from datetime import UTC, datetime

from backend.archive_lifecycle import BotoParquetArchiveStore, StorageLifecycleWorker
from backend.runtime import RuntimeServices
from backend.settings import get_settings
from backend.storage.clickhouse import EventRepository
from backend.storage.postgres import IngestMetadataRepository
from backend.worker_health import mark_worker_heartbeat

LOGGER = logging.getLogger(__name__)
SWEEP_INTERVAL_SECONDS = 30


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run archive export, restore, and partition lifecycle tasks.")
    parser.add_argument("--once", action="store_true", help="Run one lifecycle sweep and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = RuntimeServices(get_settings())
    try:
        while True:
            with runtime.postgres() as connection:
                result = StorageLifecycleWorker(
                    metadata=IngestMetadataRepository(connection),
                    events=EventRepository(runtime.clickhouse),
                    archive_store=BotoParquetArchiveStore(
                        runtime.s3,
                        bucket=runtime.settings.s3_bucket,
                        use_glacier_storage_class=runtime.settings.s3_endpoint_url is None,
                    ),
                    restore_client=runtime.restore_client,
                ).run_once(now=datetime.now(UTC))
            LOGGER.info(
                "storage lifecycle sweep archived=%s restored=%s expired=%s deleted_partitions=%s",
                result.archived_bucket_count,
                result.restored_bucket_count,
                result.expired_bucket_count,
                result.deleted_partition_count,
            )
            mark_worker_heartbeat("storage-lifecycle-worker")
            if args.once:
                return 0
            time.sleep(SWEEP_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
