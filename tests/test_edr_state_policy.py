from datetime import UTC, datetime, timedelta

import pytest

from backend.contracts.enums import EdrStateReasonCode, EdrStateStatus
from backend.policy.edr_state import (
    CollectionHealthInput,
    ThreatLevelInput,
    _collection_status,
    _threat_status,
    calculate_collection_health,
    calculate_edr_state,
    calculate_threat_level,
)

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def collection(**overrides) -> CollectionHealthInput:
    values = {
        "stale_count": 0,
        "offline_non_stale_count": 0,
        "degraded_sensor_count": 0,
        "unavailable_sensor_count": 0,
        "non_retired_endpoint_count": 1,
        "latest_ingested_at": NOW,
        "failed_count_15m": 0,
        "reprocess_failed_count_15m": 0,
        "restore_failed_bucket_count": 0,
    }
    values.update(overrides)
    return CollectionHealthInput(**values)


def test_threat_level_formula_and_reasons() -> None:
    result = calculate_threat_level(ThreatLevelInput(80, 1, 1, 1, 1))
    assert result.score == 77
    assert result.status is EdrStateStatus.RED
    assert result.reason_codes == (
        EdrStateReasonCode.HIGH_ENDPOINT_RISK,
        EdrStateReasonCode.CRITICAL_ENDPOINT_RISK,
        EdrStateReasonCode.OPEN_INCIDENT,
        EdrStateReasonCode.CRITICAL_ALERT,
    )


def test_null_highest_risk_is_zero_and_deterministic() -> None:
    input_ = ThreatLevelInput(None, 0, 0, 0, 0)
    first = calculate_threat_level(input_)
    second = calculate_threat_level(input_)
    assert first == second
    assert (first.score, first.status, first.reason_codes) == (0, EdrStateStatus.GREEN, ())


@pytest.mark.parametrize(
    ("score", "status"),
    [
        (24, EdrStateStatus.GREEN),
        (25, EdrStateStatus.YELLOW),
        (59, EdrStateStatus.YELLOW),
        (60, EdrStateStatus.RED),
    ],
)
def test_threat_status_boundaries(score: int, status: EdrStateStatus) -> None:
    assert _threat_status(score) is status


@pytest.mark.parametrize(
    ("score", "status"),
    [
        (19, EdrStateStatus.GREEN),
        (20, EdrStateStatus.YELLOW),
        (49, EdrStateStatus.YELLOW),
        (50, EdrStateStatus.RED),
    ],
)
def test_collection_status_boundaries(score: int, status: EdrStateStatus) -> None:
    assert _collection_status(score) is status


@pytest.mark.parametrize(
    ("delay", "score"),
    [
        (timedelta(minutes=2), 0),
        (timedelta(minutes=2, milliseconds=1), 10),
        (timedelta(minutes=5), 10),
        (timedelta(minutes=5, milliseconds=1), 25),
        (timedelta(minutes=15), 25),
        (timedelta(minutes=15, milliseconds=1), 40),
    ],
)
def test_ingest_delay_boundaries(delay: timedelta, score: int) -> None:
    result = calculate_collection_health(collection(latest_ingested_at=NOW - delay), calculated_at=NOW)
    assert result.score == score


def test_no_non_retired_endpoint_means_no_missing_ingest_penalty() -> None:
    result = calculate_collection_health(
        collection(non_retired_endpoint_count=0, latest_ingested_at=None), calculated_at=NOW
    )
    assert result.score == 0
    assert result.status is EdrStateStatus.GREEN


def test_stale_is_not_counted_as_offline_and_final_state_uses_worse_axis() -> None:
    threat = ThreatLevelInput(50, 1, 0, 0, 0)
    final = calculate_edr_state(
        threat,
        collection(stale_count=1, offline_non_stale_count=0),
        calculated_at=NOW,
    )
    assert final.threat_level.score == 38
    assert final.collection_health.score == 35
    assert final.status is EdrStateStatus.YELLOW
    assert final.score == 38
    assert final.reason_codes == (
        EdrStateReasonCode.HIGH_ENDPOINT_RISK,
        EdrStateReasonCode.STALE_ENDPOINT,
    )
