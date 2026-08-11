from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.storage.clickhouse import FailureRepository
from tools.replay_failure import FailureReplayInProgressError, _failure_replay_guard

NOW = datetime(2026, 7, 20, 12, tzinfo=UTC)
FAILURE_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e099")


def test_failure_replay_guard_rejects_a_concurrent_operator() -> None:
    class Result:
        def fetchone(self):
            return (False,)

    class Connection:
        def execute(self, *_args, **_kwargs):
            return Result()

    runtime = SimpleNamespace()

    @contextmanager
    def postgres():
        yield Connection()

    runtime.postgres = postgres

    with pytest.raises(FailureReplayInProgressError):
        with _failure_replay_guard(runtime, FAILURE_ID):
            pass


def test_replay_result_uses_a_monotonic_version_and_does_not_claim_completion() -> None:
    class Client:
        def __init__(self) -> None:
            self.rows = []

        def insert(self, _table, rows, *, column_names):
            self.rows.append(dict(zip(column_names, rows[0], strict=True)))

    failure = {
        "failure_id": FAILURE_ID,
        "updated_at": NOW,
        "replay_count": 0,
    }
    client = Client()

    FailureRepository(client).append_replay_result(
        failure,
        status="REPLAY_PUBLISHED",
        outcome="telemetry.raw broker acknowledged",
        replayed_at=NOW,
    )

    stored = client.rows[0]
    assert stored["updated_at"] == NOW + timedelta(milliseconds=1)
    assert stored["status"] == "REPLAY_PUBLISHED"
    assert stored["replay_count"] == 1
    assert stored["resolved_at"] is None
