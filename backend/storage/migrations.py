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
