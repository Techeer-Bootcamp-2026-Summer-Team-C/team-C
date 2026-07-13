from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.contracts.enums import EndpointRiskFactorSourceType, RiskLevel, Severity
from backend.policy.risk import (
    AlertRiskInput,
    IncidentRiskInput,
    calculate_endpoint_risk,
    risk_level,
    summarize_endpoint_risks,
)

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def alert(alert_id: int, rule: str, score: str, *, detected_delta: int = 0) -> AlertRiskInput:
    return AlertRiskInput(alert_id, rule, 1, Decimal(score), NOW + timedelta(seconds=detected_delta), rule)


def incident(incident_id: int, severity: Severity) -> IncidentRiskInput:
    return IncidentRiskInput(incident_id, f"incident-{incident_id}", severity, NOW + timedelta(seconds=incident_id))


def test_empty_endpoint_risk() -> None:
    result = calculate_endpoint_risk([], [], calculated_at=NOW)
    assert (result.score, result.level, result.highest_alert_risk_score, result.risk_factors) == (
        0,
        RiskLevel.LOW,
        None,
        (),
    )
    summary = summarize_endpoint_risks([], calculated_at=NOW)
    assert summary.highest_score is None
    assert summary.by_level == ()


def test_documented_endpoint_risk_example() -> None:
    result = calculate_endpoint_risk(
        [alert(1, "R1", "70"), alert(2, "R2", "60"), alert(3, "R3", "40")],
        [incident(1, Severity.HIGH)],
        calculated_at=NOW,
    )
    assert result.score == 99
    assert result.level is RiskLevel.CRITICAL
    assert [factor.contribution for factor in result.risk_factors] == [70, 15, 4, 10]


def test_same_rule_dedup_uses_score_then_time_then_id_but_count_is_raw() -> None:
    result = calculate_endpoint_risk(
        [alert(1, "R1", "50"), alert(2, "R1", "60", detected_delta=1), alert(3, "R2", "10")],
        [],
        calculated_at=NOW,
    )
    assert result.active_alert_count == 3
    assert result.highest_alert_risk_score == Decimal("60")
    assert result.risk_factors[0].source_id == 2


def test_round_half_up_and_cap_reduce_last_factor() -> None:
    rounded = calculate_endpoint_risk([alert(1, "R1", "10"), alert(2, "R2", "10")], [], calculated_at=NOW)
    assert [factor.contribution for factor in rounded.risk_factors] == [10, 3]
    capped = calculate_endpoint_risk(
        [alert(1, "R1", "90"), alert(2, "R2", "80")],
        [incident(1, Severity.CRITICAL)],
        calculated_at=NOW,
    )
    assert capped.score == 100
    assert [factor.contribution for factor in capped.risk_factors] == [90, 10]
    assert sum(factor.contribution for factor in capped.risk_factors) == capped.score
    assert all(factor.source_type is EndpointRiskFactorSourceType.ALERT for factor in capped.risk_factors)


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (24, RiskLevel.LOW),
        (25, RiskLevel.MEDIUM),
        (49, RiskLevel.MEDIUM),
        (50, RiskLevel.HIGH),
        (79, RiskLevel.HIGH),
        (80, RiskLevel.CRITICAL),
        (100, RiskLevel.CRITICAL),
    ],
)
def test_risk_level_boundaries(score: int, level: RiskLevel) -> None:
    assert risk_level(score) is level
