from datetime import timedelta
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator
from pydantic.json_schema import SkipJsonSchema

from .common import ContractModel, NonNegativeInt, PositiveId, UtcDateTime, validate_max_31_day_range
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
    page: int = Field(default=1, ge=1)
    size: int = Field(default=50, ge=1, le=500)


class TimeRangeQuery(ContractModel):
    time_preset: TimePreset = TimePreset.LATEST_24H
    from_: UtcDateTime | SkipJsonSchema[None] = Field(default=None, alias="from")
    to: UtcDateTime | SkipJsonSchema[None] = None

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
    endpoint_ids: list[PositiveId] | SkipJsonSchema[None] = None
    q: EndpointSearchQuery | SkipJsonSchema[None] = None
    status: Literal["ONLINE", "OFFLINE", "RETIRED"] | SkipJsonSchema[None] = None
    os_type: OsType | SkipJsonSchema[None] = None
    risk_level: RiskLevel | SkipJsonSchema[None] = None
    sort_by: Literal["riskScore", "lastSeenAt", "registeredAt"] = "riskScore"
    sort_order: Literal["asc", "desc"] = "desc"


class EventListQuery(PaginationQuery, TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = None
    event_type: EventType | SkipJsonSchema[None] = None
    process_name: str | SkipJsonSchema[None] = None
    file_path: str | SkipJsonSchema[None] = None
    domain: str | SkipJsonSchema[None] = None
    remote_ip: str | SkipJsonSchema[None] = None
    dns_query: str | SkipJsonSchema[None] = None
    l7_protocol: str | SkipJsonSchema[None] = None
    sort_order: Literal["asc", "desc"] = "desc"


class EventDetailQuery(ContractModel):
    endpoint_id: PositiveId
    occurred_at: UtcDateTime


class ProcessTreeQuery(TimeRangeQuery):
    selected_pid: NonNegativeInt | SkipJsonSchema[None] = None


class TopologyQuery(TimeRangeQuery):
    endpoint_ids: list[PositiveId] | SkipJsonSchema[None] = None


class FailureListQuery(PaginationQuery, TimeRangeQuery):
    status: EventFailureStatus | SkipJsonSchema[None] = None
    failure_stage: str | SkipJsonSchema[None] = None
    retryable: bool | SkipJsonSchema[None] = None
    sort_order: Literal["asc", "desc"] = "desc"


class ArchiveRestoreListQuery(PaginationQuery):
    endpoint_ids: list[PositiveId]
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime

    @model_validator(mode="after")
    def validate_range(self) -> "ArchiveRestoreListQuery":
        validate_max_31_day_range(self.from_, self.to)
        return self


class AlertListQuery(PaginationQuery, TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = None
    status: AlertStatus | SkipJsonSchema[None] = None
    severity: Severity | SkipJsonSchema[None] = None
    rule_code: str | SkipJsonSchema[None] = None
    sort_by: AlertSortBy = AlertSortBy.PRIORITY
    sort_order: Literal["asc", "desc"] = "desc"


class IncidentListQuery(PaginationQuery, TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = None
    status: IncidentStatus | SkipJsonSchema[None] = None
    severity: Severity | SkipJsonSchema[None] = None
    sort_order: Literal["asc", "desc"] = "desc"


class DashboardSummaryQuery(TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = None
    interval: Literal["1m", "5m", "1h", "1d"]


class DashboardTimeQuery(TimeRangeQuery):
    endpoint_id: PositiveId | SkipJsonSchema[None] = None


class CorrelationQuery(TimeRangeQuery):
    value: str
