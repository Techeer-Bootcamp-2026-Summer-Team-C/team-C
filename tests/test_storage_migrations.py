import hashlib
from unittest.mock import MagicMock

import pytest

from backend.storage.migrations import record_applied_postgres_migrations, split_sql_statements


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


def test_sql_splitter_preserves_semicolons_inside_quotes_and_dollar_blocks() -> None:
    sql = """
    -- top-level comment; must not split
    CREATE FUNCTION reject_mutation()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $append_only$
    BEGIN
        RAISE EXCEPTION 'append-only; mutation rejected';
    END;
    $append_only$;

    /* nested /* block; comment */ remains ignored */
    CREATE TRIGGER reject_update
    BEFORE UPDATE ON sample
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
    """

    statements = split_sql_statements(sql)

    assert len(statements) == 2
    assert "RAISE EXCEPTION 'append-only; mutation rejected';" in statements[0]
    assert statements[1].startswith("CREATE TRIGGER reject_update")


def test_sql_splitter_rejects_unterminated_dollar_block() -> None:
    sql = "CREATE FUNCTION broken() RETURNS void AS $body$ BEGIN;"

    try:
        split_sql_statements(sql)
    except ValueError as error:
        assert "unterminated" in str(error)
    else:
        raise AssertionError("unterminated SQL block was accepted")


def test_sql_splitter_keeps_tokens_separated_when_removing_inline_comments() -> None:
    assert split_sql_statements("SELECT/* explanation */1; SELECT 2-- note\n+ 3;") == [
        "SELECT 1",
        "SELECT 2 \n+ 3",
    ]
