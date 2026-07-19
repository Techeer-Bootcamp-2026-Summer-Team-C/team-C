from pathlib import Path

import pytest

from backend.worker_health import mark_worker_heartbeat, worker_heartbeat_is_fresh


def test_worker_heartbeat_is_fresh_within_the_allowed_age(tmp_path: Path) -> None:
    mark_worker_heartbeat("event-storage-worker", checked_at=100.0, directory=tmp_path)

    assert worker_heartbeat_is_fresh(
        "event-storage-worker",
        max_age_seconds=15,
        checked_at=115.0,
        directory=tmp_path,
    )


def test_worker_heartbeat_rejects_missing_stale_or_future_values(tmp_path: Path) -> None:
    assert not worker_heartbeat_is_fresh(
        "detection-worker",
        max_age_seconds=15,
        checked_at=100.0,
        directory=tmp_path,
    )

    mark_worker_heartbeat("detection-worker", checked_at=100.0, directory=tmp_path)
    assert not worker_heartbeat_is_fresh(
        "detection-worker",
        max_age_seconds=15,
        checked_at=115.1,
        directory=tmp_path,
    )
    assert not worker_heartbeat_is_fresh(
        "detection-worker",
        max_age_seconds=15,
        checked_at=99.0,
        directory=tmp_path,
    )


def test_worker_heartbeat_rejects_invalid_worker_and_age(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported worker"):
        mark_worker_heartbeat("unknown", directory=tmp_path)
    with pytest.raises(ValueError, match="must be positive"):
        worker_heartbeat_is_fresh(
            "storage-lifecycle-worker",
            max_age_seconds=0,
            directory=tmp_path,
        )
