from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.contracts.enums import (
    AlertStatus,
    EndpointStatus,
    IncidentStatus,
    OsType,
    Severity,
    StorageBackend,
    StorageClass,
    StorageStatus,
)


@dataclass(frozen=True, slots=True)
class EndpointInsert:
    agent_id: str
    hostname: str
    os_type: OsType
    registered_at: datetime


@dataclass(frozen=True, slots=True)
class AgentCertificateIdentity:
    subject: str
    san_agent_id: str
    fingerprint_sha256: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRegistrationResult:
    endpoint_id: int
    agent_id: str
    status: EndpointStatus
    registered_at: datetime
    created: bool


@dataclass(frozen=True, slots=True)
class EndpointAuthContext:
    endpoint_id: int
    agent_id: str
    hostname: str
    os_type: OsType
    ip_address: str | None


@dataclass(frozen=True, slots=True)
class AlertInsert:
    endpoint_id: int
    event_id: UUID
    event_occurred_at: datetime
    batch_id: UUID | None
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
    risk_score: Decimal
    detected_at: datetime


@dataclass(frozen=True, slots=True)
class IncidentInsert:
    endpoint_id: int
    correlation_key: str
    window_start_at: datetime
    window_end_at: datetime
    title: str
    description: str | None
    severity: Severity
    detected_at: datetime


@dataclass(frozen=True, slots=True)
class IngestBucket:
    endpoint_id: int
    bucket_start_at: datetime
    bucket_end_at: datetime
    storage_backend: StorageBackend
    storage_class: StorageClass
    storage_status: StorageStatus
    storage_path: str
    event_count: int = 0


@dataclass(frozen=True, slots=True)
class EventIdentity:
    event_id: UUID
    endpoint_id: int
    agent_id: str
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class StoredAlert:
    alert_id: int
    created: bool
    status: AlertStatus


@dataclass(frozen=True, slots=True)
class StoredIncident:
    incident_id: int
    created: bool
    status: IncidentStatus


JsonObject = dict[str, Any]
