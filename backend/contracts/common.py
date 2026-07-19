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
    Field(description="UTC 기준 RFC 3339 일시입니다.", examples=["2026-07-19T13:00:00Z"]),
    AfterValidator(_utc_only),
    PlainSerializer(_rfc3339_z, return_type=str, when_used="json"),
]
NonNegativeInt = Annotated[int, Field(ge=0, description="0 이상의 정수입니다.")]
PositiveId = Annotated[int, Field(ge=1, description="1 이상의 리소스 식별자입니다.")]
EndpointIdList = Annotated[
    list[PositiveId],
    Field(
        min_length=1,
        max_length=100,
        description="조회 또는 작업 대상 엔드포인트 ID 목록입니다. 중복 값은 하나로 정규화됩니다.",
        examples=[[1, 2]],
    ),
    AfterValidator(lambda values: list(dict.fromkeys(values))),
]
ScoreInt = Annotated[int, Field(ge=0, le=100, description="0부터 100까지의 정수 점수입니다.")]
ScoreNumber = Annotated[float, Field(ge=0, le=100, description="0부터 100까지의 점수입니다.")]


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
    request_id: str = Field(description="요청 추적에 사용하는 고유 ID입니다.", examples=["req_12345678"])


DataT = TypeVar("DataT")


class SuccessEnvelope(ContractModel, Generic[DataT]):
    data: DataT = Field(description="API별 성공 응답 데이터입니다.")
    meta: RequestMeta = Field(description="요청 추적 메타데이터입니다.")


class ErrorDetail(ContractModel):
    field: str | None
    message: str
    context: dict[str, Any] | None


class ErrorBody(ContractModel):
    code: str = Field(description="클라이언트가 분기 처리할 수 있는 안정적인 오류 코드입니다.")
    message: str = Field(description="오류 원인을 설명하는 메시지입니다.")
    retryable: bool = Field(description="같은 요청을 다시 시도할 수 있는지 나타냅니다.")
    details: list[ErrorDetail] = Field(description="입력 필드 등 오류의 세부 정보입니다.")


class ErrorEnvelope(ContractModel):
    error: ErrorBody
    meta: RequestMeta


ItemT = TypeVar("ItemT")


class PagedData(ContractModel, Generic[ItemT]):
    items: list[ItemT] = Field(description="현재 페이지에 포함된 항목입니다.")
    page: Annotated[int, Field(ge=1, description="현재 페이지 번호입니다.")]
    size: Annotated[int, Field(ge=1, le=500, description="페이지당 최대 항목 수입니다.")]
    total: NonNegativeInt = Field(description="조회 조건에 일치하는 전체 항목 수입니다.")
