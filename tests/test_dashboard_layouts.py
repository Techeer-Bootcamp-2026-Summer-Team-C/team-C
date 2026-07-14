from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.contracts.dashboard_layouts import DashboardLayoutPutRequest, DashboardWidgetLayoutDto
from backend.dashboard_layouts import (
    DASHBOARD_LAYOUT_VERSION,
    DashboardLayoutService,
    default_overview_widgets,
    merge_stored_overview_layout,
)
from backend.errors import ApplicationError
from backend.main import create_app


class MemoryDashboardLayoutRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str], dict[str, Any]] = {}

    def get(self, user_id: int, dashboard_key: str) -> dict[str, Any] | None:
        row = self.rows.get((user_id, dashboard_key))
        return deepcopy(row) if row is not None else None

    def upsert(
        self,
        *,
        user_id: int,
        dashboard_key: str,
        layout_version: int,
        expected_revision: int,
        widgets: list[dict[str, object]],
        now: datetime,
    ) -> int | None:
        key = (user_id, dashboard_key)
        current = self.rows.get(key)
        current_revision = int(current["revision"]) if current is not None else 0
        if current_revision != expected_revision:
            return None
        revision = current_revision + 1
        self.rows[key] = {
            "layout_version": layout_version,
            "revision": revision,
            "layout_json": deepcopy(widgets),
            "updated_at": now,
        }
        return revision

    def delete(self, user_id: int, dashboard_key: str) -> None:
        self.rows.pop((user_id, dashboard_key), None)


def _body(*, revision: int = 0, widgets: list[DashboardWidgetLayoutDto] | None = None) -> DashboardLayoutPutRequest:
    return DashboardLayoutPutRequest(
        layout_version=DASHBOARD_LAYOUT_VERSION,
        revision=revision,
        widgets=widgets or default_overview_widgets(),
    )


def test_default_layout_contains_every_registered_widget_without_overlap() -> None:
    widgets = default_overview_widgets()
    assert len(widgets) == len({widget.id for widget in widgets}) == 23
    assert all(widget.x + widget.w <= 12 for widget in widgets)
    visible = [widget for widget in widgets if not widget.hidden]
    for index, widget in enumerate(visible):
        for other in visible[:index]:
            assert (
                widget.x + widget.w <= other.x
                or other.x + other.w <= widget.x
                or widget.y + widget.h <= other.y
                or other.y + other.h <= widget.y
            )


def test_merge_adds_new_widgets_ignores_deleted_and_duplicate_ids_and_normalizes() -> None:
    stored = [
        {"id": "event-volume", "x": 99, "y": -4, "w": 99, "h": 1, "hidden": False},
        {"id": "event-volume", "x": 0, "y": 30, "w": 8, "h": 5, "hidden": True},
        {"id": "kpi-events", "x": 0, "y": 2, "w": 2, "h": 2, "hidden": "false"},
        {"id": "removed-widget", "x": 0, "y": 0, "w": 1, "h": 1, "hidden": False},
    ]
    widgets, usable = merge_stored_overview_layout(stored)
    event_volume = next(widget for widget in widgets if widget.id == "event-volume")
    events = next(widget for widget in widgets if widget.id == "kpi-events")
    assert usable is True
    assert len(widgets) == 23
    assert event_volume.w == 12
    assert event_volume.h == 4
    assert event_volume.x == 0
    assert event_volume.y >= 0
    assert event_volume.hidden is False
    assert events.hidden is False


def test_corrupted_layout_falls_back_to_default() -> None:
    widgets, usable = merge_stored_overview_layout({"widgets": "broken"})
    assert usable is False
    assert widgets == default_overview_widgets()
    widgets, usable = merge_stored_overview_layout([{"broken": True}])
    assert usable is False
    assert widgets == default_overview_widgets()


def test_layouts_are_isolated_by_authenticated_user_and_reset_is_idempotent() -> None:
    repository = MemoryDashboardLayoutRepository()
    service = DashboardLayoutService(repository)
    changed = default_overview_widgets()
    changed[0] = changed[0].model_copy(update={"hidden": True})

    saved = service.put(
        user_id=101,
        dashboard_key="overview",
        body=_body(widgets=changed),
        now=datetime.now(UTC),
    )
    assert saved.revision == 1
    assert service.get(user_id=101, dashboard_key="overview").widgets[0].hidden is True
    other = service.get(user_id=202, dashboard_key="overview")
    assert other.is_default is True
    assert other.widgets[0].hidden is False

    first_reset = service.delete(user_id=101, dashboard_key="overview")
    second_reset = service.delete(user_id=101, dashboard_key="overview")
    assert first_reset.is_default is second_reset.is_default is True
    assert first_reset.revision == second_reset.revision == 0


def test_revision_conflict_does_not_overwrite_newer_layout() -> None:
    repository = MemoryDashboardLayoutRepository()
    service = DashboardLayoutService(repository)
    service.put(user_id=1, dashboard_key="overview", body=_body(), now=datetime.now(UTC))

    with pytest.raises(ApplicationError) as caught:
        service.put(user_id=1, dashboard_key="overview", body=_body(revision=0), now=datetime.now(UTC))

    assert caught.value.status_code == 409
    assert caught.value.code == "DASHBOARD_LAYOUT_REVISION_CONFLICT"
    assert service.get(user_id=1, dashboard_key="overview").revision == 1


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda widgets: widgets.append(widgets[0].model_copy()), "Duplicate widget id"),
        (lambda widgets: widgets.__setitem__(0, widgets[0].model_copy(update={"id": "unknown"})), "Unknown widget id"),
        (lambda widgets: widgets.__setitem__(8, widgets[8].model_copy(update={"w": 5})), "size constraints"),
        (lambda widgets: widgets.__setitem__(1, widgets[1].model_copy(update={"x": 11})), "12-column grid"),
        (lambda widgets: widgets.__setitem__(1, widgets[1].model_copy(update={"y": 255})), "maximum dashboard rows"),
        (lambda widgets: widgets.__setitem__(1, widgets[1].model_copy(update={"y": 1})), "overlaps"),
    ],
)
def test_invalid_layouts_are_rejected(mutate, message: str) -> None:
    widgets = default_overview_widgets()
    mutate(widgets)
    service = DashboardLayoutService(MemoryDashboardLayoutRepository())

    with pytest.raises(ApplicationError) as caught:
        service.put(user_id=1, dashboard_key="overview", body=_body(widgets=widgets), now=datetime.now(UTC))

    assert caught.value.status_code == 400
    assert caught.value.code == "INVALID_DASHBOARD_LAYOUT"
    assert message in str(caught.value.details)


def test_dashboard_layout_endpoint_requires_authentication() -> None:
    response = TestClient(create_app()).get("/api/v1/dashboard/layouts/overview")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
