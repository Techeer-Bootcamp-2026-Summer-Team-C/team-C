from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from backend.contracts.enums import EndpointRiskFactorSourceType, RiskLevel, Severity


@dataclass(frozen=True, slots=True)
class AlertRiskInput:
    alert_id: int
    rule_code: str
    rule_version: int
    risk_score: Decimal
    detected_at: datetime
    title: str


@dataclass(frozen=True, slots=True)
class IncidentRiskInput:
    incident_id: int
    title: str
    severity: Severity
    last_detected_at: datetime


@dataclass(frozen=True, slots=True)
class RiskFactor:
    code: str
    title: str
    description: str
    contribution: int
    source_type: EndpointRiskFactorSourceType
    source_id: int


@dataclass(frozen=True, slots=True)
class EndpointRiskResult:
    score: int
    level: RiskLevel
    active_alert_count: int
    open_incident_count: int
    highest_alert_risk_score: Decimal | None
    calculated_at: datetime
    risk_factors: tuple[RiskFactor, ...]


@dataclass(frozen=True, slots=True)
class EndpointRiskSummary:
    highest_score: int | None
    high_risk_endpoint_count: int
    critical_risk_endpoint_count: int
    by_level: tuple[tuple[RiskLevel, int], ...]
    calculated_at: datetime


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def risk_level(score: int) -> RiskLevel:
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def calculate_endpoint_risk(
    active_alerts: list[AlertRiskInput],
    open_incidents: list[IncidentRiskInput],
    *,
    calculated_at: datetime,
) -> EndpointRiskResult:
    representatives: dict[tuple[str, int], AlertRiskInput] = {}
    for alert in active_alerts:
        key = (alert.rule_code, alert.rule_version)
        current = representatives.get(key)
        if current is None or (alert.risk_score, alert.detected_at, alert.alert_id) > (
            current.risk_score,
            current.detected_at,
            current.alert_id,
        ):
            representatives[key] = alert

    selected_alerts = sorted(
        representatives.values(),
        key=lambda alert: (alert.risk_score, alert.detected_at, alert.alert_id),
        reverse=True,
    )[:3]
    alert_weights = (
        ("ALERT_PRIMARY", Decimal("1"), "100%"),
        ("ALERT_SECONDARY", Decimal("0.25"), "25%"),
        ("ALERT_TERTIARY", Decimal("0.10"), "10%"),
    )

    factor_candidates: list[RiskFactor] = []
    for alert, (code, weight, label) in zip(selected_alerts, alert_weights, strict=False):
        contribution = round_half_up(alert.risk_score * weight)
        if contribution:
            factor_candidates.append(
                RiskFactor(
                    code=code,
                    title=alert.title,
                    description=f"ruleCode={alert.rule_code}, ruleVersion={alert.rule_version}, weight={label}",
                    contribution=contribution,
                    source_type=EndpointRiskFactorSourceType.ALERT,
                    source_id=alert.alert_id,
                )
            )

    severity_rank = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}
    selected_incidents = sorted(
        open_incidents,
        key=lambda incident: (severity_rank[incident.severity], incident.last_detected_at, incident.incident_id),
        reverse=True,
    )[:2]
    for incident in selected_incidents:
        factor_candidates.append(
            RiskFactor(
                code="OPEN_INCIDENT",
                title=incident.title,
                description="OPEN correlation Incident contribution",
                contribution=10,
                source_type=EndpointRiskFactorSourceType.INCIDENT,
                source_id=incident.incident_id,
            )
        )

    score = 0
    factors: list[RiskFactor] = []
    for factor in factor_candidates:
        remaining = 100 - score
        if remaining <= 0:
            break
        effective = min(factor.contribution, remaining)
        if effective <= 0:
            continue
        factors.append(
            RiskFactor(
                code=factor.code,
                title=factor.title,
                description=factor.description,
                contribution=effective,
                source_type=factor.source_type,
                source_id=factor.source_id,
            )
        )
        score += effective

    highest = max((alert.risk_score for alert in active_alerts), default=None)
    return EndpointRiskResult(
        score=score,
        level=risk_level(score),
        active_alert_count=len(active_alerts),
        open_incident_count=len(open_incidents),
        highest_alert_risk_score=highest,
        calculated_at=calculated_at,
        risk_factors=tuple(factors),
    )


def summarize_endpoint_risks(risks: list[EndpointRiskResult], *, calculated_at: datetime) -> EndpointRiskSummary:
    counts = {level: 0 for level in RiskLevel}
    for risk in risks:
        counts[risk.level] += 1
    by_level = tuple((level, counts[level]) for level in RiskLevel if counts[level] > 0)
    return EndpointRiskSummary(
        highest_score=max((risk.score for risk in risks), default=None),
        high_risk_endpoint_count=counts[RiskLevel.HIGH],
        critical_risk_endpoint_count=counts[RiskLevel.CRITICAL],
        by_level=by_level,
        calculated_at=calculated_at,
    )
