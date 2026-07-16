from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .contracts.dashboard_layouts import (
    DashboardLayoutDto,
    DashboardLayoutPutRequest,
    DashboardWidgetLayoutDto,
)
from .errors import ApplicationError

DASHBOARD_KEY_OVERVIEW = "overview"
DASHBOARD_LAYOUT_VERSION = 2
SUPPORTED_DASHBOARD_LAYOUT_VERSIONS = {1, 2}
DESKTOP_COLUMNS = 12
MAX_LAYOUT_ROWS = 256


@dataclass(frozen=True, slots=True)
class DashboardWidgetSpec:
    id: str
    x: int
    y: int
    w: int
    h: int
    min_w: int
    min_h: int
    max_w: int
    max_h: int
    hideable: bool = True


OVERVIEW_WIDGET_SPECS_V1: tuple[DashboardWidgetSpec, ...] = (
    DashboardWidgetSpec("edr-state", 0, 0, 12, 2, 6, 2, 12, 4),
    DashboardWidgetSpec("kpi-events", 0, 2, 2, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("kpi-alerts", 2, 2, 2, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("kpi-open-incidents", 4, 2, 2, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("kpi-online-endpoints", 6, 2, 2, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("kpi-event-failures", 8, 2, 2, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("kpi-storage-buckets", 10, 2, 2, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("alert-severity", 0, 4, 4, 5, 3, 4, 6, 7),
    DashboardWidgetSpec("event-volume", 4, 4, 8, 5, 6, 4, 12, 8),
    DashboardWidgetSpec("alert-volume", 0, 9, 6, 5, 6, 4, 12, 8),
    DashboardWidgetSpec("incident-activity", 6, 9, 6, 5, 6, 4, 12, 8),
    DashboardWidgetSpec("endpoint-risk", 0, 14, 4, 5, 3, 4, 6, 8),
    DashboardWidgetSpec("highest-risk-endpoints", 4, 14, 4, 5, 4, 4, 8, 8),
    DashboardWidgetSpec("incident-queue", 8, 14, 4, 5, 4, 4, 8, 8),
    DashboardWidgetSpec("response-guidance", 0, 19, 12, 5, 6, 4, 12, 9),
    DashboardWidgetSpec("endpoint-operating-systems", 0, 24, 4, 4, 3, 4, 6, 7),
    DashboardWidgetSpec("sensor-health", 4, 24, 4, 4, 3, 4, 6, 7),
    DashboardWidgetSpec("top-rules", 8, 24, 4, 4, 3, 4, 6, 7),
    DashboardWidgetSpec("mitre-distribution", 0, 28, 6, 5, 4, 4, 8, 8),
    DashboardWidgetSpec("process-network-signals", 6, 28, 6, 5, 4, 4, 8, 8),
    DashboardWidgetSpec("file-dns-l7-signals", 0, 33, 6, 5, 4, 4, 8, 8),
    DashboardWidgetSpec("failure-distribution", 6, 33, 6, 5, 4, 4, 8, 8),
    DashboardWidgetSpec("storage-distribution", 0, 38, 6, 5, 4, 4, 8, 8),
)

OVERVIEW_WIDGET_SPECS_V2: tuple[DashboardWidgetSpec, ...] = (
    DashboardWidgetSpec("edr-state", 0, 0, 12, 2, 6, 2, 12, 4),
    DashboardWidgetSpec("kpi-alerts", 0, 2, 3, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("kpi-open-incidents", 3, 2, 3, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("kpi-high-risk-endpoints", 6, 2, 3, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("kpi-event-failures", 9, 2, 3, 2, 1, 2, 4, 3),
    DashboardWidgetSpec("detection-activity", 0, 4, 8, 5, 6, 4, 12, 8),
    DashboardWidgetSpec("alert-severity", 8, 4, 4, 5, 3, 4, 6, 7),
    DashboardWidgetSpec("endpoint-risk", 0, 9, 4, 5, 3, 4, 6, 8),
    DashboardWidgetSpec("highest-risk-endpoints", 4, 9, 8, 5, 4, 4, 8, 8),
    DashboardWidgetSpec("incident-queue", 0, 14, 12, 5, 6, 4, 12, 8),
)

OVERVIEW_WIDGET_SPECS_BY_VERSION = {
    1: OVERVIEW_WIDGET_SPECS_V1,
    2: OVERVIEW_WIDGET_SPECS_V2,
}


class DashboardLayoutRepositoryPort(Protocol):
    def get(self, user_id: int, dashboard_key: str) -> dict[str, Any] | None: ...

    def upsert(
        self,
        *,
        user_id: int,
        dashboard_key: str,
        layout_version: int,
        expected_revision: int,
        widgets: list[dict[str, object]],
        now: datetime,
    ) -> int | None: ...

    def delete(self, user_id: int, dashboard_key: str) -> None: ...


def default_overview_widgets(
    layout_version: int = DASHBOARD_LAYOUT_VERSION,
) -> list[DashboardWidgetLayoutDto]:
    return [
        DashboardWidgetLayoutDto(id=spec.id, x=spec.x, y=spec.y, w=spec.w, h=spec.h, hidden=False)
        for spec in _overview_widget_specs(layout_version)
    ]


def merge_stored_overview_layout(
    value: object,
    layout_version: int = DASHBOARD_LAYOUT_VERSION,
) -> tuple[list[DashboardWidgetLayoutDto], bool]:
    specs = _overview_widget_specs(layout_version)
    spec_by_id = {spec.id: spec for spec in specs}
    if not isinstance(value, list):
        return default_overview_widgets(layout_version), False

    seen: set[str] = set()
    merged: list[DashboardWidgetLayoutDto] = []
    registry_order = {spec.id: index for index, spec in enumerate(specs)}
    for raw in value:
        if not isinstance(raw, dict):
            continue
        widget_id = raw.get("id")
        if not isinstance(widget_id, str) or widget_id in seen or widget_id not in spec_by_id:
            continue
        seen.add(widget_id)
        spec = spec_by_id[widget_id]
        merged.append(_coerce_widget(raw, spec))

    accepted_count = len(merged)

    for spec in specs:
        if spec.id not in seen:
            merged.append(
                DashboardWidgetLayoutDto(id=spec.id, x=spec.x, y=spec.y, w=spec.w, h=spec.h, hidden=False)
            )

    if accepted_count == 0:
        return default_overview_widgets(layout_version), False

    normalized = _pack_widgets(merged, registry_order)
    return normalized, True


def validate_overview_layout(body: DashboardLayoutPutRequest) -> list[DashboardWidgetLayoutDto]:
    if body.layout_version not in SUPPORTED_DASHBOARD_LAYOUT_VERSIONS:
        raise _invalid_layout("layoutVersion", "Unsupported dashboard layout version.")
    if not body.widgets:
        raise _invalid_layout("widgets", "The complete dashboard layout is required.")

    specs = _overview_widget_specs(body.layout_version)
    spec_by_id = {spec.id: spec for spec in specs}
    seen: set[str] = set()
    validated: list[DashboardWidgetLayoutDto] = []
    for widget in body.widgets:
        if widget.id in seen:
            raise _invalid_layout("widgets", f"Duplicate widget id: {widget.id}.")
        seen.add(widget.id)
        spec = spec_by_id.get(widget.id)
        if spec is None:
            raise _invalid_layout("widgets", f"Unknown widget id: {widget.id}.")
        if widget.w < spec.min_w or widget.w > spec.max_w or widget.h < spec.min_h or widget.h > spec.max_h:
            raise _invalid_layout("widgets", f"Widget {widget.id} violates its size constraints.")
        if widget.x + widget.w > DESKTOP_COLUMNS:
            raise _invalid_layout("widgets", f"Widget {widget.id} exceeds the 12-column grid.")
        if widget.y + widget.h > MAX_LAYOUT_ROWS:
            raise _invalid_layout("widgets", f"Widget {widget.id} exceeds the maximum dashboard rows.")
        if widget.hidden and not spec.hideable:
            raise _invalid_layout("widgets", f"Widget {widget.id} cannot be hidden.")
        validated.append(widget)

    visible = [widget for widget in validated if not widget.hidden]
    for index, widget in enumerate(visible):
        if any(_collides(widget, other) for other in visible[:index]):
            raise _invalid_layout("widgets", f"Widget {widget.id} overlaps another widget.")

    # A previous client may not know about a newly introduced widget. Merge it at
    # the registry default position while preserving all validated items.
    return merge_stored_overview_layout(
        [widget.model_dump() for widget in validated], body.layout_version
    )[0]


class DashboardLayoutService:
    def __init__(self, repository: DashboardLayoutRepositoryPort) -> None:
        self.repository = repository

    def get(self, *, user_id: int, dashboard_key: str) -> DashboardLayoutDto:
        _require_overview(dashboard_key)
        stored = self.repository.get(user_id, dashboard_key)
        if stored is None:
            return _response(
                layout_version=DASHBOARD_LAYOUT_VERSION,
                revision=0,
                is_default=True,
                widgets=default_overview_widgets(),
            )
        layout_version = int(stored.get("layout_version", 0))
        if layout_version not in SUPPORTED_DASHBOARD_LAYOUT_VERSIONS:
            raise ApplicationError(
                400,
                "VALIDATION_ERROR",
                "The stored dashboard layout version is not supported.",
            )
        widgets, usable = merge_stored_overview_layout(
            stored.get("layout_json"), layout_version
        )
        return _response(
            layout_version=layout_version,
            revision=int(stored["revision"]),
            is_default=not usable,
            widgets=widgets,
        )

    def put(
        self,
        *,
        user_id: int,
        dashboard_key: str,
        body: DashboardLayoutPutRequest,
        now: datetime,
    ) -> DashboardLayoutDto:
        _require_overview(dashboard_key)
        widgets = validate_overview_layout(body)
        revision = self.repository.upsert(
            user_id=user_id,
            dashboard_key=dashboard_key,
            layout_version=body.layout_version,
            expected_revision=body.revision,
            widgets=[widget.model_dump() for widget in widgets],
            now=now,
        )
        if revision is None:
            raise ApplicationError(
                409,
                "DASHBOARD_LAYOUT_REVISION_CONFLICT",
                "The dashboard layout was changed in another session. Reload it and retry.",
            )
        return _response(
            layout_version=body.layout_version,
            revision=revision,
            is_default=False,
            widgets=widgets,
        )

    def delete(self, *, user_id: int, dashboard_key: str) -> DashboardLayoutDto:
        _require_overview(dashboard_key)
        self.repository.delete(user_id, dashboard_key)
        return _response(
            layout_version=DASHBOARD_LAYOUT_VERSION,
            revision=0,
            is_default=True,
            widgets=default_overview_widgets(),
        )


def _response(
    *,
    layout_version: int,
    revision: int,
    is_default: bool,
    widgets: list[DashboardWidgetLayoutDto],
) -> DashboardLayoutDto:
    return DashboardLayoutDto(
        dashboard_key=DASHBOARD_KEY_OVERVIEW,
        layout_version=layout_version,
        revision=revision,
        is_default=is_default,
        widgets=widgets,
    )


def _coerce_widget(raw: dict[str, object], spec: DashboardWidgetSpec) -> DashboardWidgetLayoutDto:
    w = _bounded_int(raw.get("w"), spec.w, spec.min_w, min(spec.max_w, DESKTOP_COLUMNS))
    h = _bounded_int(raw.get("h"), spec.h, spec.min_h, spec.max_h)
    x = _bounded_int(raw.get("x"), spec.x, 0, DESKTOP_COLUMNS - w)
    y = _bounded_int(raw.get("y"), spec.y, 0, MAX_LAYOUT_ROWS - h)
    hidden = raw.get("hidden") is True if spec.hideable else False
    return DashboardWidgetLayoutDto(id=spec.id, x=x, y=y, w=w, h=h, hidden=hidden)


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    integer = int(value)
    return max(minimum, min(integer, maximum))


def _pack_widgets(
    widgets: list[DashboardWidgetLayoutDto], registry_order: dict[str, int]
) -> list[DashboardWidgetLayoutDto]:
    visible = sorted(
        (widget for widget in widgets if not widget.hidden),
        key=lambda widget: (widget.y, widget.x, registry_order[widget.id]),
    )
    placed: list[DashboardWidgetLayoutDto] = []
    for widget in visible:
        candidate = widget.model_copy(update={"y": 0})
        while any(_collides(candidate, other) for other in placed):
            candidate = candidate.model_copy(update={"y": candidate.y + 1})
        placed.append(candidate)
    by_id = {widget.id: widget for widget in placed}
    return [by_id.get(widget.id, widget) for widget in widgets]


def _collides(first: DashboardWidgetLayoutDto, second: DashboardWidgetLayoutDto) -> bool:
    return not (
        first.x + first.w <= second.x
        or second.x + second.w <= first.x
        or first.y + first.h <= second.y
        or second.y + second.h <= first.y
    )


def _require_overview(dashboard_key: str) -> None:
    if dashboard_key != DASHBOARD_KEY_OVERVIEW:
        raise ApplicationError(404, "DASHBOARD_LAYOUT_NOT_FOUND", "The dashboard layout key is not supported.")


def _overview_widget_specs(layout_version: int) -> tuple[DashboardWidgetSpec, ...]:
    specs = OVERVIEW_WIDGET_SPECS_BY_VERSION.get(layout_version)
    if specs is None:
        raise _invalid_layout("layoutVersion", "Unsupported dashboard layout version.")
    return specs


def _invalid_layout(field: str, message: str) -> ApplicationError:
    return ApplicationError(
        400,
        "INVALID_DASHBOARD_LAYOUT",
        "The dashboard layout is invalid.",
        details=[{"field": field, "message": message, "context": None}],
    )
