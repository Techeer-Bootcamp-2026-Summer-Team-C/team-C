from typing import Annotated, Literal

from pydantic import Field

from .common import ContractModel, NonNegativeInt

DashboardLayoutVersion = Literal[1, 2]


class DashboardWidgetLayoutDto(ContractModel):
    id: str
    x: NonNegativeInt
    y: NonNegativeInt
    w: Annotated[int, Field(ge=1, le=12)]
    h: Annotated[int, Field(ge=1, le=24)]
    hidden: bool


class DashboardLayoutPutRequest(ContractModel):
    layout_version: DashboardLayoutVersion = Field(description="레이아웃 계약 버전입니다.")
    revision: NonNegativeInt = Field(description="낙관적 동시성 제어에 사용하는 현재 revision입니다.")
    widgets: list[DashboardWidgetLayoutDto] = Field(description="저장할 위젯 배치 목록입니다.")


class DashboardLayoutDto(ContractModel):
    dashboard_key: str
    layout_version: DashboardLayoutVersion
    revision: NonNegativeInt
    is_default: bool
    widgets: list[DashboardWidgetLayoutDto]
