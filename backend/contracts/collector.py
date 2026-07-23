from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from .common import ContractModel, NonNegativeInt, PositiveId, UtcDateTime
from .enums import AgentArchitecture, EndpointStatus, EventType, OsType, SensorHealth


class AgentRegisterRequest(ContractModel):
    agent_id: Annotated[
        str,
        Field(
            pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
            description="mTLS 인증서 SAN과 일치해야 하는 Agent 고유 ID입니다.",
            examples=["agent-001"],
        ),
    ]
    hostname: str = Field(description="Agent가 설치된 호스트 이름입니다.", examples=["workstation-01"])
    os_type: OsType = Field(description="호스트 운영체제 유형입니다.")
    os_version: str = Field(description="호스트 운영체제 버전입니다.", examples=["Windows 11 24H2"])
    agent_version: str = Field(description="Agent 애플리케이션 버전입니다.", examples=["1.0.0"])
    agent_build_id: str = Field(description="배포 바이너리를 식별하는 빌드 ID입니다.", examples=["20260719.1"])
    agent_arch: AgentArchitecture = Field(description="Agent 바이너리 아키텍처입니다.")
    capability_codes: list[str] = Field(description="Agent가 지원하는 수집 기능 코드 목록입니다.")


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
    sensor: str = Field(description="상태를 보고하는 센서 이름입니다.", examples=["network"])
    status: SensorHealth = Field(description="센서의 현재 상태입니다.")
    provider: str | SkipJsonSchema[None] = Field(default=None, description="센서 구현 또는 데이터 제공자입니다.")
    packet_drop_count: NonNegativeInt | SkipJsonSchema[None] = Field(
        default=None, description="누적 패킷 유실 수입니다."
    )
    parse_error_count: NonNegativeInt | SkipJsonSchema[None] = Field(
        default=None, description="누적 파싱 오류 수입니다."
    )


class AgentHeartbeatRequest(ContractModel):
    agent_id: Annotated[
        str,
        Field(
            pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
            description="mTLS 인증서 SAN과 일치해야 하는 Agent 고유 ID입니다.",
            examples=["agent-001"],
        ),
    ]
    agent_version: str = Field(description="현재 실행 중인 Agent 버전입니다.")
    agent_build_id: str = Field(description="현재 실행 중인 Agent 빌드 ID입니다.")
    agent_arch: AgentArchitecture = Field(description="현재 실행 중인 Agent 아키텍처입니다.")
    capability_codes: list[str] = Field(description="현재 활성화된 수집 기능 코드 목록입니다.")
    buffer_depth: NonNegativeInt = Field(description="전송을 기다리는 로컬 이벤트 수입니다.")
    sensor_health: list[SensorHealthSnapshot] = Field(description="센서별 상태 스냅샷입니다.")
    sent_at: UtcDateTime = Field(description="Agent가 heartbeat를 생성한 UTC 시각입니다.")


class AgentHeartbeatData(ContractModel):
    server_time: UtcDateTime
    next_heartbeat_seconds: NonNegativeInt
    endpoint_status: EndpointStatus


class ProcessExecutionPayload(OptionalRequestFieldsModel):
    process_name: str = Field(description="실행된 프로세스 이름입니다.")
    pid: NonNegativeInt = Field(description="프로세스 ID입니다.")
    process_path: str | SkipJsonSchema[None] = Field(default=None, description="실행 파일의 절대 경로입니다.")
    ppid: NonNegativeInt | SkipJsonSchema[None] = Field(default=None, description="부모 프로세스 ID입니다.")
    command_line: str | SkipJsonSchema[None] = Field(default=None, description="프로세스 실행 명령줄입니다.")
    user_name: str | SkipJsonSchema[None] = Field(default=None, description="프로세스를 실행한 사용자 이름입니다.")


class NetworkConnectionPayload(OptionalRequestFieldsModel):
    protocol: str = Field(description="전송 계층 프로토콜입니다.", examples=["TCP"])
    remote_ip: str = Field(description="원격 IPv4 또는 IPv6 주소입니다.", examples=["203.0.113.10"])
    remote_port: Annotated[int, Field(ge=0, le=65535, description="원격 포트 번호입니다.")]
    remote_domain: str | SkipJsonSchema[None] = Field(default=None, description="확인된 원격 Domain입니다.")
    process_name: str | SkipJsonSchema[None] = Field(default=None, description="통신을 생성한 프로세스 이름입니다.")
    pid: NonNegativeInt | SkipJsonSchema[None] = Field(default=None, description="통신을 생성한 프로세스 ID입니다.")


class FileEventPayload(OptionalRequestFieldsModel):
    file_path: str = Field(description="관찰된 파일의 절대 경로입니다.")
    action: Literal["CREATE", "DELETE", "MODIFY", "RENAME"] = Field(
        description="파일에 수행된 정규화된 동작입니다.",
        examples=["CREATE"],
    )
    sha256: str | SkipJsonSchema[None] = Field(default=None, description="파일 내용의 SHA-256 해시입니다.")
    process_name: str | SkipJsonSchema[None] = Field(
        default=None, description="파일 동작을 수행한 프로세스 이름입니다."
    )
    pid: NonNegativeInt | SkipJsonSchema[None] = Field(
        default=None, description="파일 동작을 수행한 프로세스 ID입니다."
    )

    @field_validator("action", mode="before")
    @classmethod
    def normalize_legacy_action(cls, value: object) -> object:
        if isinstance(value, str):
            return {
                "CREATED": "CREATE",
                "DELETED": "DELETE",
                "MODIFIED": "MODIFY",
                "RENAMED": "RENAME",
            }.get(value.upper(), value.upper())
        return value


class DnsQueryPayload(OptionalRequestFieldsModel):
    query: str = Field(description="DNS 질의 이름입니다.", examples=["example.com"])
    record_type: str = Field(description="DNS 레코드 유형입니다.", examples=["A"])
    response_code: str | SkipJsonSchema[None] = Field(default=None, description="DNS 응답 코드입니다.")
    answers: list[str] | SkipJsonSchema[None] = Field(default=None, description="DNS 응답 값 목록입니다.")
    process_name: str | SkipJsonSchema[None] = Field(default=None, description="DNS 질의를 생성한 프로세스 이름입니다.")
    pid: NonNegativeInt | SkipJsonSchema[None] = Field(default=None, description="DNS 질의를 생성한 프로세스 ID입니다.")


class L7EventPayload(OptionalRequestFieldsModel):
    l7_protocol: str = Field(description="응용 계층 프로토콜입니다.", examples=["HTTP"])
    http_method: str | SkipJsonSchema[None] = Field(default=None, description="HTTP 요청 메서드입니다.")
    http_host: str | SkipJsonSchema[None] = Field(default=None, description="HTTP Host 값입니다.")
    url: str | SkipJsonSchema[None] = Field(default=None, description="관찰된 요청 URL입니다.")
    http_status_code: int | SkipJsonSchema[None] = Field(default=None, description="HTTP 응답 상태 코드입니다.")
    http_user_agent: str | SkipJsonSchema[None] = Field(default=None, description="HTTP User-Agent 값입니다.")
    tls_sni: str | SkipJsonSchema[None] = Field(default=None, description="TLS SNI 값입니다.")
    tls_version: str | SkipJsonSchema[None] = Field(default=None, description="협상된 TLS 버전입니다.")
    tls_certificate_subject: str | SkipJsonSchema[None] = Field(default=None, description="서버 인증서 Subject입니다.")
    tls_certificate_issuer: str | SkipJsonSchema[None] = Field(default=None, description="서버 인증서 Issuer입니다.")
    tls_certificate_sha256: str | SkipJsonSchema[None] = Field(
        default=None, description="서버 인증서 DER 값의 SHA-256 해시입니다."
    )


class ProcessExecutionEvent(ContractModel):
    event_id: str = Field(description="Agent가 생성한 이벤트 고유 ID입니다.")
    event_type: Literal[EventType.PROCESS_EXECUTION] = Field(description="프로세스 실행 이벤트 유형입니다.")
    occurred_at: UtcDateTime = Field(description="이벤트가 엔드포인트에서 발생한 UTC 시각입니다.")
    payload: ProcessExecutionPayload = Field(description="프로세스 실행 세부 정보입니다.")


class NetworkConnectionEvent(ContractModel):
    event_id: str = Field(description="Agent가 생성한 이벤트 고유 ID입니다.")
    event_type: Literal[EventType.NETWORK_CONNECTION] = Field(description="네트워크 연결 이벤트 유형입니다.")
    occurred_at: UtcDateTime = Field(description="이벤트가 엔드포인트에서 발생한 UTC 시각입니다.")
    payload: NetworkConnectionPayload = Field(description="네트워크 연결 세부 정보입니다.")


class FileEvent(ContractModel):
    event_id: str = Field(description="Agent가 생성한 이벤트 고유 ID입니다.")
    event_type: Literal[EventType.FILE_EVENT] = Field(description="파일 이벤트 유형입니다.")
    occurred_at: UtcDateTime = Field(description="이벤트가 엔드포인트에서 발생한 UTC 시각입니다.")
    payload: FileEventPayload = Field(description="파일 동작 세부 정보입니다.")


class DnsQueryEvent(ContractModel):
    event_id: str = Field(description="Agent가 생성한 이벤트 고유 ID입니다.")
    event_type: Literal[EventType.DNS_QUERY] = Field(description="DNS 질의 이벤트 유형입니다.")
    occurred_at: UtcDateTime = Field(description="이벤트가 엔드포인트에서 발생한 UTC 시각입니다.")
    payload: DnsQueryPayload = Field(description="DNS 질의 세부 정보입니다.")


class L7Event(ContractModel):
    event_id: str = Field(description="Agent가 생성한 이벤트 고유 ID입니다.")
    event_type: Literal[EventType.L7_EVENT] = Field(description="응용 계층 이벤트 유형입니다.")
    occurred_at: UtcDateTime = Field(description="이벤트가 엔드포인트에서 발생한 UTC 시각입니다.")
    payload: L7EventPayload = Field(description="응용 계층 통신 세부 정보입니다.")


TelemetryEvent = Annotated[
    ProcessExecutionEvent | NetworkConnectionEvent | FileEvent | DnsQueryEvent | L7Event,
    Field(discriminator="event_type", description="eventType으로 구분되는 텔레메트리 이벤트입니다."),
]


class TelemetryBatchRequest(ContractModel):
    schema_version: Literal[1] = Field(description="텔레메트리 계약 버전입니다.")
    batch_id: str = Field(description="재전송 중복 제거에 사용하는 배치 고유 ID입니다.")
    agent_id: Annotated[
        str,
        Field(
            pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
            description="mTLS 인증서 SAN과 일치해야 하는 Agent 고유 ID입니다.",
            examples=["agent-001"],
        ),
    ]
    sent_at: UtcDateTime = Field(description="Agent가 배치를 전송한 UTC 시각입니다.")
    events: Annotated[
        list[TelemetryEvent],
        Field(min_length=1, max_length=100, description="1개 이상 100개 이하의 텔레메트리 이벤트입니다."),
    ]


class RejectedEventDto(ContractModel):
    event_id: str
    code: str
    message: str
    retryable: bool


class TelemetryBatchData(ContractModel):
    batch_id: str
    accepted_event_ids: list[str]
    rejected_events: list[RejectedEventDto]
