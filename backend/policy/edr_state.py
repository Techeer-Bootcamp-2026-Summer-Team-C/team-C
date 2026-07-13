from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from backend.contracts.enums import EdrStateReasonCode, EdrStateStatus

from .risk import risk_level, round_half_up


@dataclass(frozen=True, slots=True)
class ThreatLevelInput:
    highest_endpoint_risk_score: int | None
    high_risk_endpoint_count: int
    critical_risk_endpoint_count: int
    open_incident_count: int
    critical_open_alert_count: int


@dataclass(frozen=True, slots=True)
class CollectionHealthInput:
    stale_count: int
    offline_non_stale_count: int
    degraded_sensor_count: int
    unavailable_sensor_count: int
    non_retired_endpoint_count: int
    latest_ingested_at: datetime | None
    failed_count_15m: int
    reprocess_failed_count_15m: int
    restore_failed_bucket_count: int


@dataclass(frozen=True, slots=True)
class EdrStateAxisResult:
    status: EdrStateStatus
    score: int
    reason_codes: tuple[EdrStateReasonCode, ...]


@dataclass(frozen=True, slots=True)
class EdrStateResult:
    status: EdrStateStatus
    score: int
    threat_level: EdrStateAxisResult
    collection_health: EdrStateAxisResult
    highest_endpoint_risk_score: int | None
    high_risk_endpoint_count: int
    critical_risk_endpoint_count: int
    reason_codes: tuple[EdrStateReasonCode, ...]
    calculated_at: datetime


def _threat_status(score: int) -> EdrStateStatus:
    if score >= 60:
        return EdrStateStatus.RED
    if score >= 25:
        return EdrStateStatus.YELLOW
    return EdrStateStatus.GREEN


def _collection_status(score: int) -> EdrStateStatus:
    if score >= 50:
        return EdrStateStatus.RED
    if score >= 20:
        return EdrStateStatus.YELLOW
    return EdrStateStatus.GREEN


def calculate_threat_level(input_: ThreatLevelInput) -> EdrStateAxisResult:
    highest = input_.highest_endpoint_risk_score or 0
    raw = (
        Decimal(highest) * Decimal("0.70")
        + Decimal(min(input_.high_risk_endpoint_count * 3, 15))
        + Decimal(min(input_.critical_risk_endpoint_count * 10, 20))
        + Decimal(min(input_.open_incident_count * 3, 15))
        + Decimal(min(input_.critical_open_alert_count * 5, 20))
    )
    score = round_half_up(min(raw, Decimal(100)))
    reasons: list[EdrStateReasonCode] = []
    if risk_level(highest).value == "MEDIUM":
        reasons.append(EdrStateReasonCode.MEDIUM_ENDPOINT_RISK)
    if input_.high_risk_endpoint_count > 0:
        reasons.append(EdrStateReasonCode.HIGH_ENDPOINT_RISK)
    if input_.critical_risk_endpoint_count > 0:
        reasons.append(EdrStateReasonCode.CRITICAL_ENDPOINT_RISK)
    if input_.open_incident_count > 0:
        reasons.append(EdrStateReasonCode.OPEN_INCIDENT)
    if input_.critical_open_alert_count > 0:
        reasons.append(EdrStateReasonCode.CRITICAL_ALERT)
    return EdrStateAxisResult(_threat_status(score), score, tuple(reasons))


def _ingest_delay_contribution(input_: CollectionHealthInput, calculated_at: datetime) -> int:
    if input_.non_retired_endpoint_count == 0:
        return 0
    if input_.latest_ingested_at is None:
        return 40
    delay = calculated_at - input_.latest_ingested_at
    if delay <= timedelta(minutes=2):
        return 0
    if delay <= timedelta(minutes=5):
        return 10
    if delay <= timedelta(minutes=15):
        return 25
    return 40


def calculate_collection_health(input_: CollectionHealthInput, *, calculated_at: datetime) -> EdrStateAxisResult:
    ingest_delay = _ingest_delay_contribution(input_, calculated_at)
    contributions = (
        min(input_.stale_count * 35, 70),
        min(input_.offline_non_stale_count * 20, 40),
        min(input_.degraded_sensor_count * 10, 20),
        min(input_.unavailable_sensor_count * 25, 50),
        ingest_delay,
        min(input_.failed_count_15m * 5, 20),
        min(input_.reprocess_failed_count_15m * 10, 20),
        min(input_.restore_failed_bucket_count * 20, 40),
    )
    score = min(sum(contributions), 100)
    reasons: list[EdrStateReasonCode] = []
    if input_.offline_non_stale_count > 0:
        reasons.append(EdrStateReasonCode.OFFLINE_ENDPOINT)
    if input_.stale_count > 0:
        reasons.append(EdrStateReasonCode.STALE_ENDPOINT)
    if input_.degraded_sensor_count > 0:
        reasons.append(EdrStateReasonCode.DEGRADED_SENSOR)
    if input_.unavailable_sensor_count > 0:
        reasons.append(EdrStateReasonCode.UNAVAILABLE_SENSOR)
    if input_.failed_count_15m > 0 or input_.reprocess_failed_count_15m > 0:
        reasons.append(EdrStateReasonCode.INGEST_FAILURE)
    if ingest_delay > 0:
        reasons.append(EdrStateReasonCode.INGEST_DELAYED)
    if input_.restore_failed_bucket_count > 0:
        reasons.append(EdrStateReasonCode.STORAGE_FAILURE)
    return EdrStateAxisResult(_collection_status(score), score, tuple(reasons))


def calculate_edr_state(
    threat_input: ThreatLevelInput,
    collection_input: CollectionHealthInput,
    *,
    calculated_at: datetime,
) -> EdrStateResult:
    threat = calculate_threat_level(threat_input)
    collection = calculate_collection_health(collection_input, calculated_at=calculated_at)
    priority = {EdrStateStatus.GREEN: 0, EdrStateStatus.YELLOW: 1, EdrStateStatus.RED: 2}
    status = max((threat.status, collection.status), key=priority.__getitem__)
    present = set(threat.reason_codes) | set(collection.reason_codes)
    reasons = tuple(code for code in EdrStateReasonCode if code in present)
    return EdrStateResult(
        status=status,
        score=max(threat.score, collection.score),
        threat_level=threat,
        collection_health=collection,
        highest_endpoint_risk_score=threat_input.highest_endpoint_risk_score,
        high_risk_endpoint_count=threat_input.high_risk_endpoint_count,
        critical_risk_endpoint_count=threat_input.critical_risk_endpoint_count,
        reason_codes=reasons,
        calculated_at=calculated_at,
    )
