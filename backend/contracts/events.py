from typing import Any

from .common import ContractModel, NonNegativeInt, PositiveId, UtcDateTime
from .enums import EventType, OsType


class EventDto(ContractModel):
    event_id: str
    batch_id: str
    endpoint_id: PositiveId
    agent_id: str
    hostname: str
    os_type: OsType
    ip_address: str | None
    event_type: EventType
    occurred_at: UtcDateTime
    ingested_at: UtcDateTime
    process_name: str | None
    process_path: str | None
    pid: NonNegativeInt | None
    ppid: NonNegativeInt | None
    command_line: str | None
    user_name: str | None
    file_path: str | None
    file_action: str | None
    file_hash_sha256: str | None
    remote_ip: str | None
    remote_domain: str | None
    remote_port: int | None
    protocol: str | None
    dns_query: str | None
    dns_record_type: str | None
    dns_response_code: str | None
    dns_answers: list[str]
    l7_protocol: str | None
    http_method: str | None
    http_host: str | None
    url: str | None
    http_status_code: int | None
    http_user_agent: str | None
    tls_sni: str | None
    tls_version: str | None
    tls_certificate_subject: str | None
    tls_certificate_issuer: str | None
    tls_certificate_sha256: str | None


class EventDetailDto(EventDto):
    raw_payload: dict[str, Any]
    payload_sha256: str
    schema_version: NonNegativeInt
