from collections.abc import Callable

import pytest

from tools import prod_init


class TransientError(Exception):
    pass


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
