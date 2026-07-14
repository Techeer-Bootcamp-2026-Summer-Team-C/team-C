from typing import Annotated

from pydantic import Field

from .common import ContractModel, NonNegativeInt


class DashboardWidgetLayoutDto(ContractModel):
    id: str
    x: NonNegativeInt
    y: NonNegativeInt
    w: Annotated[int, Field(ge=1, le=12)]
    h: Annotated[int, Field(ge=1, le=24)]
    hidden: bool


class DashboardLayoutPutRequest(ContractModel):
    layout_version: Annotated[int, Field(ge=1)]
    revision: NonNegativeInt
    widgets: list[DashboardWidgetLayoutDto]


class DashboardLayoutDto(ContractModel):
    dashboard_key: str
    layout_version: Annotated[int, Field(ge=1)]
    revision: NonNegativeInt
    is_default: bool
    widgets: list[DashboardWidgetLayoutDto]
