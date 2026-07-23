import hashlib
from unittest.mock import MagicMock

import pytest

from backend.storage.migrations import record_applied_postgres_migrations


def _query_rows(*rows: tuple[str, str]) -> MagicMock:
    result = MagicMock()
    result.fetchall.return_value = list(rows)
    return result


def test_record_applied_postgres_migrations_records_all_up_files(tmp_path) -> None:
    first = tmp_path / "0001_initial.up.sql"
    second = tmp_path / "0002_extra.up.sql"
    first.write_text("SELECT 1;\n", encoding="utf-8")
    second.write_text("SELECT 2;\n", encoding="utf-8")
    connection = MagicMock()
    connection.execute.side_effect = [MagicMock(), _query_rows(), MagicMock(), MagicMock()]

    record_applied_postgres_migrations(connection, tmp_path)

    inserts = [
        call.args[1]
        for call in connection.execute.call_args_list
        if "INSERT INTO schema_migrations" in call.args[0]
    ]
    assert inserts == [
        (first.name, hashlib.sha256(first.read_bytes()).hexdigest()),
        (second.name, hashlib.sha256(second.read_bytes()).hexdigest()),
    ]
    assert connection.commit.call_count == 2


def test_record_applied_postgres_migrations_accepts_matching_existing_checksum(tmp_path) -> None:
    migration = tmp_path / "0001_initial.up.sql"
    migration.write_text("SELECT 1;\n", encoding="utf-8")
    checksum = hashlib.sha256(migration.read_bytes()).hexdigest()
    connection = MagicMock()
    connection.execute.side_effect = [MagicMock(), _query_rows((migration.name, checksum))]

    record_applied_postgres_migrations(connection, tmp_path)

    assert all(
        "INSERT INTO schema_migrations" not in call.args[0]
        for call in connection.execute.call_args_list
    )


def test_record_applied_postgres_migrations_rejects_checksum_drift(tmp_path) -> None:
    migration = tmp_path / "0001_initial.up.sql"
    migration.write_text("SELECT 1;\n", encoding="utf-8")
    connection = MagicMock()
    connection.execute.side_effect = [MagicMock(), _query_rows((migration.name, "0" * 64))]

    with pytest.raises(RuntimeError, match="checksum drift"):
        record_applied_postgres_migrations(connection, tmp_path)
