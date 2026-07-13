from .common import ContractModel, NonNegativeInt, PositiveId, ScoreInt, ScoreNumber, UtcDateTime
from .enums import (
    AgentArchitecture,
    EndpointRiskFactorSourceType,
    EndpointStatus,
    OsType,
    RiskLevel,
    SensorHealth,
)


class SensorHealthDto(ContractModel):
    sensor: str
    status: SensorHealth
    provider: str | None
    packet_drop_count: NonNegativeInt | None
    parse_error_count: NonNegativeInt | None


class EndpointRiskFactorDto(ContractModel):
    code: str
    title: str
    description: str
    contribution: NonNegativeInt
    source_type: EndpointRiskFactorSourceType
    source_id: PositiveId


class EndpointRiskDto(ContractModel):
    score: ScoreInt
    level: RiskLevel
    active_alert_count: NonNegativeInt
    open_incident_count: NonNegativeInt
    highest_alert_risk_score: ScoreNumber | None
    calculated_at: UtcDateTime
    risk_factors: list[EndpointRiskFactorDto]


class EndpointDto(ContractModel):
    endpoint_id: PositiveId
    agent_id: str
    hostname: str
    os_type: OsType
    os_version: str | None
    ip_address: str | None
    agent_version: str | None
    agent_build_id: str | None
    agent_arch: AgentArchitecture | None
    capability_codes: list[str]
    status: EndpointStatus
    last_seen_at: UtcDateTime | None
    is_stale: bool
    sensor_health: list[SensorHealthDto]
    risk: EndpointRiskDto
    registered_at: UtcDateTime


class CertificateDto(ContractModel):
    cert_fingerprint: str
    cert_subject: str
    cert_san_agent_id: str
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    revoked_at: UtcDateTime | None
    is_expired: bool
    is_revoked: bool


class EndpointDetailDto(EndpointDto):
    certificates: list[CertificateDto]
