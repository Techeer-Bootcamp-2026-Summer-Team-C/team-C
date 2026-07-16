from typing import Literal

from pydantic import Field

from .common import ContractModel, NonNegativeInt, PositiveId, ScoreInt, ScoreNumber, UtcDateTime
from .dashboard import TimeRangeDto
from .enums import (
    EndpointStatus,
    EventFailureStatus,
    EventType,
    InvestigationEvidence,
    InvestigationNodeType,
    InvestigationRelation,
    InvestigationWarningCode,
    RiskLevel,
    Severity,
)


class EventFailureDto(ContractModel):
    failure_id: str
    event_id: str
    endpoint_id: PositiveId
    source_topic: str
    source_partition: NonNegativeInt
    source_offset: NonNegativeInt
    consumer_name: str
    failure_stage: str
    failure_code: str | None
    error_message: str
    retryable: bool
    retry_count: NonNegativeInt
    payload_object_key: str | None
    payload_sha256: str | None
    payload_size_bytes: NonNegativeInt | None
    status: EventFailureStatus
    failed_at: UtcDateTime
    replay_count: NonNegativeInt
    last_replayed_at: UtcDateTime | None
    reprocess_outcome: str | None
    resolved_at: UtcDateTime | None
    retention_expires_at: UtcDateTime
    created_at: UtcDateTime
    updated_at: UtcDateTime


class TopologyNodeDto(ContractModel):
    endpoint_id: PositiveId
    hostname: str
    status: EndpointStatus
    risk_score: ScoreInt
    risk_level: RiskLevel
    alert_count: NonNegativeInt


class TopologyEdgeDto(ContractModel):
    endpoint_id: PositiveId
    source_label: str
    target: str
    protocol: str
    event_count: NonNegativeInt
    alert_count: NonNegativeInt
    last_seen_at: UtcDateTime


class EgressTopologyDto(ContractModel):
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime
    nodes: list[TopologyNodeDto]
    edges: list[TopologyEdgeDto]


class AttackTimelineItemDto(ContractModel):
    item_type: Literal["INCIDENT", "EVENT", "ALERT"]
    occurred_at: UtcDateTime
    endpoint_id: PositiveId
    title: str
    summary: str
    severity: Severity | None
    event_type: EventType | None
    event_id: str | None
    alert_id: PositiveId | None
    incident_id: PositiveId | None


class AttackTimelineDto(ContractModel):
    incident_id: PositiveId
    endpoint_id: PositiveId
    items: list[AttackTimelineItemDto]


class InvestigationNodeDto(ContractModel):
    node_id: str
    node_type: InvestigationNodeType
    label: str
    endpoint_id: PositiveId | None
    incident_id: PositiveId | None
    alert_id: PositiveId | None
    event_id: str | None
    pid: NonNegativeInt | None
    process_name: str | None
    destination: str | None
    protocol: str | None
    occurred_at: UtcDateTime | None
    severity: Severity | None
    event_type: EventType | None
    risk_score: ScoreNumber | None


class InvestigationEdgeDto(ContractModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: InvestigationRelation
    evidence: InvestigationEvidence
    incident_id: PositiveId | None
    alert_id: PositiveId | None
    event_id: str | None
    observed_at: UtcDateTime | None


class InvestigationWarningDto(ContractModel):
    code: InvestigationWarningCode
    message: str
    event_id: str | None
    endpoint_id: PositiveId | None
    occurred_at: UtcDateTime | None


class InvestigationFallbackDto(ContractModel):
    timeline_available: bool
    alert_table_available: bool
    event_table_available: bool


class IncidentInvestigationDto(ContractModel):
    incident_id: PositiveId
    time_range: TimeRangeDto
    nodes: list[InvestigationNodeDto]
    edges: list[InvestigationEdgeDto]
    node_count: NonNegativeInt
    edge_count: NonNegativeInt
    truncated: bool
    partial: bool
    warnings: list[InvestigationWarningDto]
    fallback: InvestigationFallbackDto
