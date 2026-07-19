from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools import prod_init


class TransientError(Exception):
    pass


def query_result(value: object) -> MagicMock:
    result = MagicMock()
    result.fetchone.return_value = (value,)
    return result


def test_retry_dependency_retries_selected_transient_errors() -> None:
    calls = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientError("not ready")
        return "ready"

    result = prod_init.retry_dependency(
        "dependency",
        operation,
        retry_on=(TransientError,),
        attempts=4,
        initial_delay_seconds=1,
        max_delay_seconds=2,
        sleep=delays.append,
    )

    assert result == "ready"
    assert calls == 3
    assert delays == [1, 2]


def test_retry_dependency_does_not_hide_unexpected_errors() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("invalid migration")

    with pytest.raises(ValueError, match="invalid migration"):
        prod_init.retry_dependency(
            "dependency",
            operation,
            retry_on=(TransientError,),
            sleep=lambda _delay: None,
        )

    assert calls == 1


def test_retry_dependency_stops_after_the_configured_attempts() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise TransientError("still unavailable")

    with pytest.raises(TransientError, match="still unavailable"):
        prod_init.retry_dependency(
            "dependency",
            operation,
            retry_on=(TransientError,),
            attempts=3,
            sleep=lambda _delay: None,
        )

    assert calls == 3


@pytest.mark.parametrize(
    ("query_values", "expected_migrations"),
    [
        (
            [None, False, False, None, 64],
            [
                "0001_initial.up.sql",
                "0002_user_login_id.up.sql",
                "0003_user_locale.up.sql",
                "0004_user_dashboard_layouts.up.sql",
                "0005_query_search_sort_indexes.up.sql",
                "0006_backend_hardening.up.sql",
            ],
        ),
        (
            ["users", True, True, "user_dashboard_layouts", 64],
            ["0005_query_search_sort_indexes.up.sql", "0006_backend_hardening.up.sql"],
        ),
    ],
    ids=("fresh-database", "existing-database"),
)
def test_initialize_postgres_applies_only_missing_migrations(
    monkeypatch: pytest.MonkeyPatch,
    query_values: list[object],
    expected_migrations: list[str],
) -> None:
    connection = MagicMock()
    connection.execute.side_effect = [query_result(value) for value in query_values]
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    applied: list[str] = []
    settings = SimpleNamespace(
        postgres_dsn=SimpleNamespace(get_secret_value=lambda: "postgresql://example")
    )

    monkeypatch.setattr(prod_init.psycopg, "connect", lambda _dsn: connection_context)
    monkeypatch.setattr(
        prod_init,
        "apply_postgres_file",
        lambda _connection, path: applied.append(path.name),
    )
    monkeypatch.setattr(prod_init, "_apply_versioned_postgres_migrations", lambda _connection: None)

    prod_init.initialize_postgres(settings)

    assert applied == expected_migrations
    executed_queries = [call.args[0] for call in connection.execute.call_args_list]
    assert "SELECT to_regclass('public.user_dashboard_layouts')" in executed_queries


def test_main_checks_dependencies_before_running_initializers(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = object()
    events: list[str] = []

    monkeypatch.setattr(prod_init, "get_settings", lambda: settings)
    for name in ("check_postgres", "check_clickhouse", "check_kafka"):
        monkeypatch.setattr(prod_init, name, _recording_call(name, events))
    for name in ("initialize_postgres", "initialize_clickhouse", "initialize_kafka"):
        monkeypatch.setattr(prod_init, name, _recording_call(name, events))

    assert prod_init.main() == 0
    assert events == [
        "check_postgres",
        "check_clickhouse",
        "check_kafka",
        "initialize_postgres",
        "initialize_clickhouse",
        "initialize_kafka",
    ]


def _recording_call(name: str, events: list[str]) -> Callable[[object], None]:
    def record(_settings: object) -> None:
        events.append(name)

    return record
