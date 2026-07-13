from typing import Annotated, Literal

from pydantic import Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from .common import ContractModel, NonNegativeInt, PositiveId, UtcDateTime
from .enums import AgentArchitecture, EndpointStatus, EventType, OsType, SensorHealth


class AgentRegisterRequest(ContractModel):
    agent_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
    hostname: str
    os_type: OsType
    os_version: str
    agent_version: str
    agent_build_id: str
    agent_arch: AgentArchitecture
    capability_codes: list[str]


class AgentRegisterData(ContractModel):
    endpoint_id: PositiveId
    agent_id: str
    status: EndpointStatus
    heartbeat_interval_seconds: NonNegativeInt
    registered_at: UtcDateTime


class OptionalRequestFieldsModel(ContractModel):
    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if isinstance(value, dict):
            null_fields = [key for key, item in value.items() if item is None]
            if null_fields:
                raise ValueError(f"optional request fields must be omitted, not null: {', '.join(null_fields)}")
        return value


class SensorHealthSnapshot(OptionalRequestFieldsModel):
    sensor: str
    status: SensorHealth
    provider: str | SkipJsonSchema[None] = None
    packet_drop_count: NonNegativeInt | SkipJsonSchema[None] = None
    parse_error_count: NonNegativeInt | SkipJsonSchema[None] = None


class AgentHeartbeatRequest(ContractModel):
    agent_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
    agent_version: str
    agent_build_id: str
    agent_arch: AgentArchitecture
    capability_codes: list[str]
    buffer_depth: NonNegativeInt
    sensor_health: list[SensorHealthSnapshot]
    sent_at: UtcDateTime


class AgentHeartbeatData(ContractModel):
    server_time: UtcDateTime
    next_heartbeat_seconds: NonNegativeInt
    endpoint_status: EndpointStatus


class ProcessExecutionPayload(OptionalRequestFieldsModel):
    process_name: str
    pid: NonNegativeInt
    process_path: str | SkipJsonSchema[None] = None
    ppid: NonNegativeInt | SkipJsonSchema[None] = None
    command_line: str | SkipJsonSchema[None] = None
    user_name: str | SkipJsonSchema[None] = None


class NetworkConnectionPayload(OptionalRequestFieldsModel):
    protocol: str
    remote_ip: str
    remote_port: Annotated[int, Field(ge=0, le=65535)]
    remote_domain: str | SkipJsonSchema[None] = None
    process_name: str | SkipJsonSchema[None] = None
    pid: NonNegativeInt | SkipJsonSchema[None] = None


class FileEventPayload(OptionalRequestFieldsModel):
    file_path: str
    action: str
    sha256: str | SkipJsonSchema[None] = None
    process_name: str | SkipJsonSchema[None] = None
    pid: NonNegativeInt | SkipJsonSchema[None] = None


class DnsQueryPayload(OptionalRequestFieldsModel):
    query: str
    record_type: str
    response_code: str | SkipJsonSchema[None] = None
    answers: list[str] | SkipJsonSchema[None] = None
    process_name: str | SkipJsonSchema[None] = None
    pid: NonNegativeInt | SkipJsonSchema[None] = None


class L7EventPayload(OptionalRequestFieldsModel):
    l7_protocol: str
    http_method: str | SkipJsonSchema[None] = None
    http_host: str | SkipJsonSchema[None] = None
    url: str | SkipJsonSchema[None] = None
    http_status_code: int | SkipJsonSchema[None] = None
    http_user_agent: str | SkipJsonSchema[None] = None
    tls_sni: str | SkipJsonSchema[None] = None
    tls_version: str | SkipJsonSchema[None] = None
    tls_certificate_subject: str | SkipJsonSchema[None] = None
    tls_certificate_issuer: str | SkipJsonSchema[None] = None
    tls_certificate_sha256: str | SkipJsonSchema[None] = None


class ProcessExecutionEvent(ContractModel):
    event_id: str
    event_type: Literal[EventType.PROCESS_EXECUTION]
    occurred_at: UtcDateTime
    payload: ProcessExecutionPayload


class NetworkConnectionEvent(ContractModel):
    event_id: str
    event_type: Literal[EventType.NETWORK_CONNECTION]
    occurred_at: UtcDateTime
    payload: NetworkConnectionPayload


class FileEvent(ContractModel):
    event_id: str
    event_type: Literal[EventType.FILE_EVENT]
    occurred_at: UtcDateTime
    payload: FileEventPayload


class DnsQueryEvent(ContractModel):
    event_id: str
    event_type: Literal[EventType.DNS_QUERY]
    occurred_at: UtcDateTime
    payload: DnsQueryPayload


class L7Event(ContractModel):
    event_id: str
    event_type: Literal[EventType.L7_EVENT]
    occurred_at: UtcDateTime
    payload: L7EventPayload


TelemetryEvent = Annotated[
    ProcessExecutionEvent | NetworkConnectionEvent | FileEvent | DnsQueryEvent | L7Event,
    Field(discriminator="event_type"),
]


class TelemetryBatchRequest(ContractModel):
    schema_version: Literal[1]
    batch_id: str
    agent_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
    sent_at: UtcDateTime
    events: Annotated[list[TelemetryEvent], Field(min_length=1, max_length=100)]


class RejectedEventDto(ContractModel):
    event_id: str
    code: str
    message: str
    retryable: bool


class TelemetryBatchData(ContractModel):
    batch_id: str
    accepted_event_ids: list[str]
    rejected_events: list[RejectedEventDto]
