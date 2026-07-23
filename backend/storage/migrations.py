import hashlib
from pathlib import Path
from typing import Literal, Protocol

from psycopg import Connection as PostgresConnection


class ClickHouseCommandClient(Protocol):
    def command(self, command: str) -> object: ...


def split_sql_statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def apply_postgres_file(connection: PostgresConnection, path: Path) -> None:
    with connection.transaction():
        for statement in split_sql_statements(path.read_text(encoding="utf-8")):
            connection.execute(statement)


def apply_postgres_migrations(
    connection: PostgresConnection,
    directory: Path,
    *,
    direction: Literal["up", "down"] = "up",
) -> None:
    paths = sorted(directory.glob(f"*.{direction}.sql"), reverse=direction == "down")
    for path in paths:
        apply_postgres_file(connection, path)


def apply_clickhouse_file(client: ClickHouseCommandClient, path: Path) -> None:
    for statement in split_sql_statements(path.read_text(encoding="utf-8")):
        client.command(statement)


def record_applied_postgres_migrations(
    connection: PostgresConnection,
    directory: Path,
) -> None:
    """Record every migration after a verified full-reset apply without running it twice."""
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
    recorded = {
        str(row[0]): str(row[1])
        for row in connection.execute(
            "SELECT migration_name, checksum_sha256 FROM schema_migrations"
        ).fetchall()
    }
    for path in sorted(directory.glob("*.up.sql")):
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        existing = recorded.get(path.name)
        if existing is not None and existing != checksum:
            raise RuntimeError(f"PostgreSQL migration checksum drift: {path.name}")
        if existing is None:
            connection.execute(
                "INSERT INTO schema_migrations (migration_name, checksum_sha256) VALUES (%s, %s)",
                (path.name, checksum),
            )
    connection.commit()
