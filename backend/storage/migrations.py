import hashlib
from pathlib import Path
from typing import Literal, Protocol

from psycopg import Connection as PostgresConnection


class ClickHouseCommandClient(Protocol):
    def command(self, command: str) -> object: ...


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    quote: str | None = None
    dollar_tag: str | None = None
    block_comment_depth = 0
    line_comment = False

    while index < len(sql):
        char = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
                buffer.append(char)
            index += 1
            continue
        if block_comment_depth:
            if char == "/" and following == "*":
                block_comment_depth += 1
                index += 2
            elif char == "*" and following == "/":
                block_comment_depth -= 1
                index += 2
            else:
                index += 1
            continue
        if dollar_tag is not None:
            if sql.startswith(dollar_tag, index):
                buffer.append(dollar_tag)
                index += len(dollar_tag)
                dollar_tag = None
            else:
                buffer.append(char)
                index += 1
            continue
        if quote is not None:
            buffer.append(char)
            if char == quote:
                if following == quote:
                    buffer.append(following)
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char == "-" and following == "-":
            if buffer and not buffer[-1].isspace():
                buffer.append(" ")
            line_comment = True
            index += 2
            continue
        if char == "/" and following == "*":
            if buffer and not buffer[-1].isspace():
                buffer.append(" ")
            block_comment_depth = 1
            index += 2
            continue
        if char in {"'", '"'}:
            quote = char
            buffer.append(char)
            index += 1
            continue
        if char == "$":
            closing = sql.find("$", index + 1)
            if closing != -1:
                candidate = sql[index : closing + 1]
                tag = candidate[1:-1]
                if not tag or (tag.replace("_", "a").isalnum() and not tag[0].isdigit()):
                    dollar_tag = candidate
                    buffer.append(candidate)
                    index = closing + 1
                    continue
        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer.clear()
        else:
            buffer.append(char)
        index += 1

    if quote is not None or dollar_tag is not None or block_comment_depth:
        raise ValueError("unterminated quoted string or comment in SQL migration")
    statement = "".join(buffer).strip()
    if statement:
        statements.append(statement)
    return statements


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
