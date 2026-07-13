from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel


def _utc_only(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include UTC timezone information")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must use UTC")
    return value.astimezone(UTC)


def _rfc3339_z(value: datetime) -> str:
    timespec = "milliseconds" if value.microsecond else "seconds"
    rendered = value.astimezone(UTC).isoformat(timespec=timespec)
    return rendered.removesuffix("+00:00") + "Z"


UtcDateTime = Annotated[
    datetime,
    AfterValidator(_utc_only),
    PlainSerializer(_rfc3339_z, return_type=str, when_used="json"),
]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveId = Annotated[int, Field(ge=1)]
ScoreInt = Annotated[int, Field(ge=0, le=100)]
ScoreNumber = Annotated[float, Field(ge=0, le=100)]


def validate_max_31_day_range(from_: datetime, to: datetime) -> None:
    if from_ >= to:
        raise ValueError("from must be before to")
    if to - from_ > timedelta(days=31):
        raise ValueError("range must not exceed 31 days")


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        validate_assignment=True,
    )


class RequestMeta(ContractModel):
    request_id: str


DataT = TypeVar("DataT")


class SuccessEnvelope(ContractModel, Generic[DataT]):
    data: DataT
    meta: RequestMeta


class ErrorDetail(ContractModel):
    field: str | None
    message: str
    context: dict[str, Any] | None


class ErrorBody(ContractModel):
    code: str
    message: str
    retryable: bool
    details: list[ErrorDetail]


class ErrorEnvelope(ContractModel):
    error: ErrorBody
    meta: RequestMeta


ItemT = TypeVar("ItemT")


class PagedData(ContractModel, Generic[ItemT]):
    items: list[ItemT]
    page: Annotated[int, Field(ge=1)]
    size: Annotated[int, Field(ge=1, le=500)]
    total: NonNegativeInt
