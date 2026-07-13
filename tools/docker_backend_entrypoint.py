from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import clickhouse_connect
import psycopg
from botocore.exceptions import ClientError

ROOT = Path(__file__).parents[1]


def _initialize(*, attempts: int = 10, delay_seconds: float = 3.0) -> None:
    import boto3

    from backend.kafka import ensure_topics
    from backend.settings import get_settings
    from backend.storage.migrations import apply_clickhouse_file, apply_postgres_file

    settings = get_settings()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with psycopg.connect(settings.postgres_dsn.get_secret_value()) as connection:
                exists = connection.execute("SELECT to_regclass('public.users')").fetchone()[0]
                if exists is None:
                    apply_postgres_file(connection, ROOT / "migrations/postgresql/0001_initial.up.sql")
                refresh_sessions_exists = connection.execute(
                    "SELECT to_regclass('public.refresh_sessions')"
                ).fetchone()[0]
                if refresh_sessions_exists is None:
                    apply_postgres_file(connection, ROOT / "migrations/postgresql/0002_refresh_sessions.up.sql")

            clickhouse = clickhouse_connect.get_client(
                dsn=settings.clickhouse_dsn.get_secret_value(), autogenerate_session_id=False
            )
            try:
                apply_clickhouse_file(clickhouse, ROOT / "migrations/clickhouse/0001_initial.up.sql")
            finally:
                clickhouse.close()

            s3 = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
                aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
                region_name="us-east-1",
            )
            try:
                s3.create_bucket(Bucket=settings.s3_bucket)
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") not in {
                    "BucketAlreadyExists",
                    "BucketAlreadyOwnedByYou",
                }:
                    raise

            ensure_topics(settings.kafka_bootstrap_servers)
            return
        except Exception as error:  # noqa: BLE001
            last_error = error
            print(f"backend init attempt {attempt}/{attempts} failed: {error}", file=sys.stderr)
            time.sleep(delay_seconds)
    raise RuntimeError(f"backend init failed after {attempts} attempts") from last_error


def main() -> None:
    _initialize()
    os.execvp("uvicorn", ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"])


if __name__ == "__main__":
    main()
