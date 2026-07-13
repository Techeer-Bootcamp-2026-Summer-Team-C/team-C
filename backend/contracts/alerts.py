from .common import ContractModel, PositiveId, ScoreNumber, UtcDateTime
from .enums import AlertStatus, IncidentStatus, Severity
from .events import EventDto


class AlertDto(ContractModel):
    alert_id: PositiveId
    endpoint_id: PositiveId
    event_id: str
    event_occurred_at: UtcDateTime
    batch_id: str | None
    agent_id: str
    rule_code: str
    rule_name: str
    rule_version: int
    mitre_tactic_code: str
    mitre_tactic_name: str
    mitre_technique_code: str
    mitre_technique_name: str
    title: str
    summary: str
    severity: Severity
    risk_score: ScoreNumber
    status: AlertStatus
    detected_at: UtcDateTime
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ResponseGuidanceStepDto(ContractModel):
    order: int
    title: str
    description: str
    requires_manual_action: bool


class IncidentReferenceDto(ContractModel):
    incident_id: PositiveId
    title: str
    severity: Severity
    status: IncidentStatus
    window_start_at: UtcDateTime
    window_end_at: UtcDateTime


class AlertDetailDto(AlertDto):
    source_event: EventDto | None
    incidents: list[IncidentReferenceDto]
    response_guidance: list[ResponseGuidanceStepDto]


class AlertStatusUpdateRequest(ContractModel):
    status: AlertStatus
