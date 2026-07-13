from typing import Annotated

from pydantic import Field

from .alerts import ResponseGuidanceStepDto
from .common import ContractModel, NonNegativeInt, ScoreInt, UtcDateTime
from .enums import (
    AlertStatus,
    DashboardInterval,
    EdrStateReasonCode,
    EdrStateStatus,
    EventFailureStatus,
    EventType,
    OsType,
    RiskLevel,
    SensorHealth,
    Severity,
    StorageBackend,
    StorageClass,
    StorageStatus,
)


class TimeRangeDto(ContractModel):
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime


class SeverityCountDto(ContractModel):
    severity: Severity
    count: NonNegativeInt


class AlertStatusCountDto(ContractModel):
    status: AlertStatus
    count: NonNegativeInt


class EventTypeCountDto(ContractModel):
    event_type: EventType
    count: NonNegativeInt


class FailureStatusCountDto(ContractModel):
    status: EventFailureStatus
    count: NonNegativeInt


class StorageBackendCountDto(ContractModel):
    storage_backend: StorageBackend
    count: NonNegativeInt


class StorageClassCountDto(ContractModel):
    storage_class: StorageClass
    count: NonNegativeInt


class StorageStatusCountDto(ContractModel):
    storage_status: StorageStatus
    count: NonNegativeInt


class OsTypeCountDto(ContractModel):
    os_type: OsType
    count: NonNegativeInt


class SensorHealthCountDto(ContractModel):
    sensor: str
    status: SensorHealth
    count: NonNegativeInt


class TimeSeriesPointDto(ContractModel):
    bucket_start_at: UtcDateTime
    count: NonNegativeInt


class IncidentTimeSeriesPointDto(ContractModel):
    bucket_start_at: UtcDateTime
    open_count: NonNegativeInt
    closed_count: NonNegativeInt


class TopRuleDto(ContractModel):
    rule_code: str
    rule_name: str
    count: NonNegativeInt


class MitreTacticCountDto(ContractModel):
    mitre_tactic_code: str
    mitre_tactic_name: str
    count: NonNegativeInt


class MitreTechniqueCountDto(ContractModel):
    mitre_technique_code: str
    mitre_technique_name: str
    count: NonNegativeInt


class TopProcessDto(ContractModel):
    process_name: str
    count: NonNegativeInt


class TopRemoteIpDto(ContractModel):
    remote_ip: str
    count: NonNegativeInt


class TopDomainDto(ContractModel):
    domain: str
    count: NonNegativeInt


class TopFileHashDto(ContractModel):
    file_hash_sha256: str
    count: NonNegativeInt


class TopDnsQueryDto(ContractModel):
    dns_query: str
    count: NonNegativeInt


class TopL7ProtocolDto(ContractModel):
    l7_protocol: str
    count: NonNegativeInt


class FailureStageCountDto(ContractModel):
    failure_stage: str
    count: NonNegativeInt


class FailureCodeCountDto(ContractModel):
    failure_code: str | None
    count: NonNegativeInt


class RiskLevelCountDto(ContractModel):
    level: RiskLevel
    count: NonNegativeInt


class EndpointRiskSummaryDto(ContractModel):
    highest_score: ScoreInt | None
    high_risk_endpoint_count: NonNegativeInt
    critical_risk_endpoint_count: NonNegativeInt
    by_level: list[RiskLevelCountDto]
    calculated_at: UtcDateTime


class EdrStateAxisDto(ContractModel):
    status: EdrStateStatus
    score: ScoreInt
    reason_codes: list[EdrStateReasonCode]


class EdrStateDto(ContractModel):
    status: EdrStateStatus
    score: ScoreInt
    threat_level: EdrStateAxisDto
    collection_health: EdrStateAxisDto
    highest_endpoint_risk_score: ScoreInt | None
    high_risk_endpoint_count: NonNegativeInt
    critical_risk_endpoint_count: NonNegativeInt
    reason_codes: list[EdrStateReasonCode]
    calculated_at: UtcDateTime


class DashboardAlertsDto(ContractModel):
    total_count: NonNegativeInt
    by_severity: list[SeverityCountDto]
    by_status: list[AlertStatusCountDto]
    top_rules: list[TopRuleDto]
    mitre_tactics: list[MitreTacticCountDto]
    mitre_techniques: list[MitreTechniqueCountDto]
    time_series: list[TimeSeriesPointDto]


class DashboardIncidentsDto(ContractModel):
    open_count: NonNegativeInt
    closed_count: NonNegativeInt
    by_severity: list[SeverityCountDto]
    time_series: list[IncidentTimeSeriesPointDto]


class DashboardEndpointsDto(ContractModel):
    total_count: NonNegativeInt
    online_count: NonNegativeInt
    offline_count: NonNegativeInt
    retired_count: NonNegativeInt
    stale_count: NonNegativeInt


class DashboardEventsDto(ContractModel):
    total_count: NonNegativeInt
    by_event_type: list[EventTypeCountDto]
    top_processes: list[TopProcessDto]
    top_remote_ips: list[TopRemoteIpDto]
    top_domains: list[TopDomainDto]
    top_file_hashes: list[TopFileHashDto]
    top_dns_queries: list[TopDnsQueryDto]
    top_l7_protocols: list[TopL7ProtocolDto]
    time_series: list[TimeSeriesPointDto]


class DashboardEventFailuresDto(ContractModel):
    total_count: NonNegativeInt
    by_stage: list[FailureStageCountDto]
    by_code: list[FailureCodeCountDto]
    by_status: list[FailureStatusCountDto]


class DashboardStorageDto(ContractModel):
    total_bucket_count: NonNegativeInt
    by_backend: list[StorageBackendCountDto]
    by_class: list[StorageClassCountDto]
    by_status: list[StorageStatusCountDto]


class ResponseGuidanceSummaryDto(ContractModel):
    affected_alert_count: NonNegativeInt
    rule_count: NonNegativeInt
    manual_action_step_count: NonNegativeInt
    highest_severity: Severity | None
    steps: list[ResponseGuidanceStepDto]


class DashboardSummaryDto(ContractModel):
    time_range: TimeRangeDto
    interval: DashboardInterval
    edr_state: EdrStateDto
    alerts: DashboardAlertsDto
    incidents: DashboardIncidentsDto
    endpoints: DashboardEndpointsDto
    events: DashboardEventsDto
    event_failures: DashboardEventFailuresDto
    storage: DashboardStorageDto
    response_guidance: ResponseGuidanceSummaryDto


class EndpointSummaryAlertsDto(ContractModel):
    total_count: NonNegativeInt
    by_severity: list[SeverityCountDto]


class EndpointSummaryIncidentsDto(ContractModel):
    total_count: NonNegativeInt
    open_count: NonNegativeInt
    closed_count: NonNegativeInt
    by_severity: list[SeverityCountDto]


class EndpointSummaryDto(ContractModel):
    time_range: TimeRangeDto
    total_count: NonNegativeInt
    online_count: NonNegativeInt
    offline_count: NonNegativeInt
    retired_count: NonNegativeInt
    stale_count: NonNegativeInt
    by_os_type: list[OsTypeCountDto]
    sensor_health: list[SensorHealthCountDto]
    risk: EndpointRiskSummaryDto
    alerts: EndpointSummaryAlertsDto
    incidents: EndpointSummaryIncidentsDto


class IngestEventsDto(ContractModel):
    ingested_count: NonNegativeInt
    rate_per_minute: Annotated[float, Field(ge=0)]
    latest_ingested_at: UtcDateTime | None


class IngestEventFailuresDto(ContractModel):
    failed_count: NonNegativeInt
    rate_per_minute: Annotated[float, Field(ge=0)]
    reprocessed_count: NonNegativeInt
    reprocess_failed_count: NonNegativeInt
    oldest_failed_at: UtcDateTime | None


class IngestStorageDto(ContractModel):
    clickhouse_hot_bucket_count: NonNegativeInt
    restored_bucket_count: NonNegativeInt
    glacier_archived_bucket_count: NonNegativeInt
    restoring_bucket_count: NonNegativeInt
    failed_bucket_count: NonNegativeInt
    expired_bucket_count: NonNegativeInt


class IngestSummaryDto(ContractModel):
    time_range: TimeRangeDto
    events: IngestEventsDto
    event_failures: IngestEventFailuresDto
    storage: IngestStorageDto
