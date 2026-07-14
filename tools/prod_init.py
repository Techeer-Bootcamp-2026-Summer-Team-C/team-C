from pathlib import Path

import clickhouse_connect
import psycopg

from backend.kafka import ensure_topics
from backend.settings import Settings, get_settings
from backend.storage.migrations import apply_clickhouse_file, apply_postgres_file

ROOT = Path(__file__).parents[1]


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

        login_id_length = connection.execute(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'login_id'
            """
        ).fetchone()[0]
        if login_id_length != 64:
            connection.execute("ALTER TABLE users ALTER COLUMN login_id TYPE VARCHAR(64)")


def initialize_clickhouse(settings: Settings) -> None:
    client = clickhouse_connect.get_client(
        dsn=settings.clickhouse_dsn.get_secret_value(),
        autogenerate_session_id=False,
    )
    try:
        apply_clickhouse_file(client, ROOT / "migrations/clickhouse/0001_initial.up.sql")
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
    initialize_postgres(settings)
    initialize_clickhouse(settings)
    initialize_kafka(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
