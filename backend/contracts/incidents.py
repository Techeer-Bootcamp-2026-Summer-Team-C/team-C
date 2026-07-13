from .alerts import AlertDto
from .common import ContractModel, NonNegativeInt, PositiveId, UtcDateTime
from .enums import IncidentStatus, Severity


class IncidentDto(ContractModel):
    incident_id: PositiveId
    endpoint_id: PositiveId
    correlation_key: str
    window_start_at: UtcDateTime
    window_end_at: UtcDateTime
    title: str
    description: str | None
    severity: Severity
    status: IncidentStatus
    first_detected_at: UtcDateTime
    last_detected_at: UtcDateTime
    closed_at: UtcDateTime | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    alert_count: NonNegativeInt


class IncidentDetailDto(IncidentDto):
    alerts: list[AlertDto]
