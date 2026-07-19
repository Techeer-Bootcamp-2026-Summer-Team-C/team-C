from datetime import timedelta
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator
from pydantic.json_schema import SkipJsonSchema

from .common import ContractModel, EndpointIdList, NonNegativeInt, PositiveId, UtcDateTime, validate_max_31_day_range
from .enums import (
    AlertSortBy,
    AlertStatus,
    EventFailureStatus,
    EventType,
    IncidentStatus,
    OsType,
    RiskLevel,
    Severity,
    TimePreset,
)

EndpointSearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class PaginationQuery(ContractModel):
    page: int = Field(default=1, ge=1, description="조회할 페이지 번호입니다.")
    size: int = Field(default=50, ge=1, le=500, description="페이지당 항목 수입니다.")


class TimeRangeQuery(ContractModel):
    time_preset: TimePreset = Field(
        default=TimePreset.LATEST_24H,
        description="조회 시간 프리셋입니다. CUSTOM이면 from과 to를 모두 지정해야 합니다.",
    )
    from_: UtcDateTime | SkipJsonSchema[None] = Field(
        default=None,
        alias="from",
        description="CUSTOM 조회 범위의 시작 시각입니다.",
    )
    to: UtcDateTime | SkipJsonSchema[None] = Field(
        default=None,
        description="CUSTOM 조회 범위의 종료 시각입니다. 최대 조회 범위는 31일입니다.",
    )

    @model_validator(mode="after")
    def validate_range(self) -> "TimeRangeQuery":
        if self.time_preset is TimePreset.CUSTOM:
            if self.from_ is None or self.to is None:
                raise ValueError("CUSTOM requires from and to")
            if self.from_ >= self.to:
                raise ValueError("from must be before to")
            if self.to - self.from_ > timedelta(days=31):
                raise ValueError("CUSTOM range must not exceed 31 days")
        return self


class EndpointListQuery(PaginationQuery):
    endpoint_ids: EndpointIdList | SkipJsonSchema[None] = Field(default=None, description="조회할 엔드포인트 ID입니다.")
    q: EndpointSearchQuery | SkipJsonSchema[None] = Field(
        default=None,
        description="hostname, Agent ID 또는 IP 주소를 검색합니다.",
        examples=["workstation-01"],
    )
    status: Literal["ONLINE", "OFFLINE", "RETIRED"] | SkipJsonSchema[None] = Field(
        default=None, description="엔드포인트 연결 상태 필터입니다."
    )
    os_type: OsType | SkipJsonSchema[None] = Field(default=None, description="운영체제 유형 필터입니다.")
    risk_level: RiskLevel | SkipJsonSchema[None] = Field(default=None, description="백엔드 산정 위험도 필터입니다.")
    sort_by: Literal["riskScore", "lastSeenAt", "registeredAt"] = Field(
        default="riskScore", description="목록 정렬 기준입니다."
    )
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="정렬 방향입니다.")


class EventListQuery(PaginationQuery, TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = Field(
        default=None, description="특정 엔드포인트의 이벤트만 조회합니다."
    )
    event_type: EventType | SkipJsonSchema[None] = Field(default=None, description="이벤트 유형 필터입니다.")
    process_name: str | SkipJsonSchema[None] = Field(default=None, description="프로세스 이름 검색 조건입니다.")
    file_path: str | SkipJsonSchema[None] = Field(default=None, description="파일 경로 검색 조건입니다.")
    domain: str | SkipJsonSchema[None] = Field(default=None, description="원격 Domain 검색 조건입니다.")
    remote_ip: str | SkipJsonSchema[None] = Field(default=None, description="원격 IP 주소 검색 조건입니다.")
    dns_query: str | SkipJsonSchema[None] = Field(default=None, description="DNS 질의값 검색 조건입니다.")
    l7_protocol: str | SkipJsonSchema[None] = Field(default=None, description="L7 프로토콜 검색 조건입니다.")
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="이벤트 발생 시각 정렬 방향입니다.")


class EventDetailQuery(ContractModel):
    endpoint_id: PositiveId = Field(description="이벤트가 발생한 엔드포인트 ID입니다.")
    occurred_at: UtcDateTime = Field(description="이벤트가 발생한 UTC 시각입니다.")


class ProcessTreeQuery(TimeRangeQuery):
    selected_pid: NonNegativeInt | SkipJsonSchema[None] = Field(
        default=None, description="지정하면 해당 PID를 중심으로 프로세스 트리를 표시합니다."
    )


class TopologyQuery(TimeRangeQuery):
    endpoint_ids: EndpointIdList | SkipJsonSchema[None] = Field(
        default=None, description="지정한 엔드포인트의 외부 통신만 집계합니다."
    )


class FailureListQuery(PaginationQuery, TimeRangeQuery):
    status: EventFailureStatus | SkipJsonSchema[None] = Field(default=None, description="실패 처리 상태 필터입니다.")
    failure_stage: str | SkipJsonSchema[None] = Field(default=None, description="실패가 발생한 파이프라인 단계입니다.")
    retryable: bool | SkipJsonSchema[None] = Field(default=None, description="재처리 가능 여부 필터입니다.")
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="실패 발생 시각 정렬 방향입니다.")


class ArchiveRestoreListQuery(PaginationQuery):
    endpoint_ids: EndpointIdList = Field(description="복원 상태를 조회할 엔드포인트 ID입니다.")
    from_: UtcDateTime = Field(alias="from", description="조회 범위의 시작 시각입니다.")
    to: UtcDateTime = Field(description="조회 범위의 종료 시각입니다. 최대 조회 범위는 31일입니다.")

    @model_validator(mode="after")
    def validate_range(self) -> "ArchiveRestoreListQuery":
        validate_max_31_day_range(self.from_, self.to)
        return self


class AlertListQuery(PaginationQuery, TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = Field(
        default=None, description="특정 엔드포인트의 Alert만 조회합니다."
    )
    status: AlertStatus | SkipJsonSchema[None] = Field(default=None, description="Alert 처리 상태 필터입니다.")
    severity: Severity | SkipJsonSchema[None] = Field(default=None, description="Alert 심각도 필터입니다.")
    rule_code: str | SkipJsonSchema[None] = Field(default=None, description="탐지 규칙 코드 필터입니다.")
    sort_by: AlertSortBy = Field(default=AlertSortBy.PRIORITY, description="Alert 정렬 기준입니다.")
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="정렬 방향입니다.")


class IncidentListQuery(PaginationQuery, TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = Field(
        default=None, description="특정 엔드포인트의 Incident만 조회합니다."
    )
    status: IncidentStatus | SkipJsonSchema[None] = Field(default=None, description="Incident 상태 필터입니다.")
    severity: Severity | SkipJsonSchema[None] = Field(default=None, description="Incident 심각도 필터입니다.")
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="정렬 방향입니다.")


class DashboardSummaryQuery(TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = Field(
        default=None, description="특정 엔드포인트 지표만 집계합니다."
    )
    interval: Literal["1m", "5m", "1h", "1d"] = Field(description="시계열 집계 간격입니다.")


class DashboardTimeQuery(TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = Field(
        default=None, description="특정 엔드포인트 지표만 집계합니다."
    )


class CorrelationQuery(TimeRangeQuery):
    value: str = Field(description="상관분석할 IP 주소 또는 Domain입니다.", examples=["example.com"])
    endpoint_ids: EndpointIdList | SkipJsonSchema[None] = Field(
        default=None, description="지정한 엔드포인트에서 관찰된 관계만 조회합니다."
    )
