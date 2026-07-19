import hashlib
import sys
import time
from collections.abc import Callable
from pathlib import Path

import clickhouse_connect
import psycopg
from clickhouse_connect.driver.exceptions import ClickHouseError
from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient

from backend.kafka import ensure_topics
from backend.settings import Settings, get_settings
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_file

ROOT = Path(__file__).parents[1]
POSTGRES_BASELINE_MIGRATIONS = {
    "0001_initial.up.sql",
    "0002_user_login_id.up.sql",
    "0003_user_locale.up.sql",
    "0004_user_dashboard_layouts.up.sql",
    "0005_query_search_sort_indexes.up.sql",
    "0006_backend_hardening.up.sql",
}


def retry_dependency[T](
    name: str,
    operation: Callable[[], T],
    *,
    retry_on: tuple[type[Exception], ...],
    attempts: int = 10,
    initial_delay_seconds: float = 1.0,
    max_delay_seconds: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry a dependency readiness probe without hiding application errors."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    delay = initial_delay_seconds
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retry_on as exc:
            if attempt == attempts:
                raise
            print(
                f"{name} is not ready ({attempt}/{attempts}): {exc}; retrying in {delay:g}s",
                file=sys.stderr,
                flush=True,
            )
            sleep(delay)
            delay = min(delay * 2, max_delay_seconds)

    raise AssertionError("retry loop exited unexpectedly")


def check_postgres(settings: Settings) -> None:
    with psycopg.connect(settings.postgres_dsn.get_secret_value(), connect_timeout=5):
        pass


def check_clickhouse(settings: Settings) -> None:
    client = clickhouse_connect.get_client(
        dsn=settings.clickhouse_dsn.get_secret_value(),
        autogenerate_session_id=False,
        connect_timeout=5,
    )
    try:
        client.command("SELECT 1")
    finally:
        client.close()


def check_kafka(settings: Settings) -> None:
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    admin.list_topics(timeout=5)


def initialize_postgres(settings: Settings) -> None:
    with psycopg.connect(settings.postgres_dsn.get_secret_value()) as connection:
        users_table = connection.execute("SELECT to_regclass('public.users')").fetchone()[0]
        if users_table is None:
            apply_postgres_file(connection, ROOT / "migrations/postgresql/0001_initial.up.sql")

        login_id_exists = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'login_id'
            )
            """
        ).fetchone()[0]
        if not login_id_exists:
            apply_postgres_file(connection, ROOT / "migrations/postgresql/0002_user_login_id.up.sql")

        locale_exists = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'locale'
            )
            """
        ).fetchone()[0]
        if not locale_exists:
            apply_postgres_file(connection, ROOT / "migrations/postgresql/0003_user_locale.up.sql")

        dashboard_layouts_table = connection.execute(
            "SELECT to_regclass('public.user_dashboard_layouts')"
        ).fetchone()[0]
        if dashboard_layouts_table is None:
            apply_postgres_file(connection, ROOT / "migrations/postgresql/0004_user_dashboard_layouts.up.sql")

        apply_postgres_file(connection, ROOT / "migrations/postgresql/0005_query_search_sort_indexes.up.sql")
        apply_postgres_file(connection, ROOT / "migrations/postgresql/0006_backend_hardening.up.sql")

        login_id_length = connection.execute(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'login_id'
            """
        ).fetchone()[0]
        if login_id_length != 64:
            connection.execute("ALTER TABLE users ALTER COLUMN login_id TYPE VARCHAR(64)")
        _apply_versioned_postgres_migrations(connection)


def _apply_versioned_postgres_migrations(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_name TEXT PRIMARY KEY,
            checksum_sha256 CHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    migration_paths = sorted((ROOT / "migrations/postgresql").glob("*.up.sql"))
    applied = {
        str(row[0]): str(row[1])
        for row in connection.execute(
            "SELECT migration_name, checksum_sha256 FROM schema_migrations"
        ).fetchall()
    }
    if not applied:
        for path in migration_paths:
            if path.name in POSTGRES_BASELINE_MIGRATIONS:
                checksum = hashlib.sha256(path.read_bytes()).hexdigest()
                connection.execute(
                    "INSERT INTO schema_migrations (migration_name, checksum_sha256) VALUES (%s, %s)",
                    (path.name, checksum),
                )
        connection.commit()
        applied = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT migration_name, checksum_sha256 FROM schema_migrations"
            ).fetchall()
        }
    for path in migration_paths:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        recorded = applied.get(path.name)
        if recorded is not None:
            if recorded != checksum:
                raise RuntimeError(f"PostgreSQL migration checksum drift: {path.name}")
            continue
        apply_postgres_file(connection, path)
        connection.execute(
            "INSERT INTO schema_migrations (migration_name, checksum_sha256) VALUES (%s, %s)",
            (path.name, checksum),
        )
        connection.commit()


def initialize_clickhouse(settings: Settings) -> None:
    client = clickhouse_connect.get_client(
        dsn=settings.clickhouse_dsn.get_secret_value(),
        autogenerate_session_id=False,
    )
    try:
        for path in sorted((ROOT / "migrations/clickhouse").glob("*.up.sql")):
            apply_clickhouse_file(client, path)
    finally:
        client.close()


def initialize_kafka(settings: Settings) -> None:
    ensure_topics(
        settings.kafka_bootstrap_servers,
        topics=settings.kafka_topics,
        partitions_per_topic=settings.kafka_partitions_per_topic,
        replication_factor=settings.kafka_replication_factor,
    )


def main() -> int:
    settings = get_settings()
    retry_dependency(
        "PostgreSQL",
        lambda: check_postgres(settings),
        retry_on=(psycopg.OperationalError,),
    )
    retry_dependency(
        "ClickHouse",
        lambda: check_clickhouse(settings),
        retry_on=(ClickHouseError,),
    )
    retry_dependency(
        "Kafka",
        lambda: check_kafka(settings),
        retry_on=(KafkaException,),
    )
    initialize_postgres(settings)
    initialize_clickhouse(settings)
    initialize_kafka(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
