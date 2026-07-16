from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.contracts.enums import (
    EventType,
    InvestigationEvidence,
    InvestigationNodeType,
    InvestigationRelation,
    InvestigationWarningCode,
)
from backend.errors import ApplicationError
from backend.investigation_service import MAX_INVESTIGATION_EDGES, MAX_INVESTIGATION_NODES, InvestigationService

NOW = datetime(2026, 7, 15, 3, tzinfo=UTC)


def _incident() -> dict:
    return {
        "endpoint_id": 1,
        "window_start_at": NOW,
        "window_end_at": NOW + timedelta(hours=1),
        "first_detected_at": NOW,
        "title": "Observed command chain",
        "severity": "HIGH",
    }


def _alert(alert_id: int, event_id: str, *, minute: int) -> dict:
    return {
        "alert_id": alert_id,
        "endpoint_id": 1,
        "event_id": event_id,
        "event_occurred_at": NOW + timedelta(minutes=minute),
        "detected_at": NOW + timedelta(minutes=minute, seconds=30),
        "title": f"Alert {alert_id}",
        "severity": "HIGH",
        "risk_score": 80 + alert_id % 20,
    }


def _event(
    event_id: str,
    *,
    minute: int,
    pid: int,
    ppid: int | None,
    process_name: str,
    destination: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        event_id=event_id,
        endpoint_id=1,
        event_type=EventType.NETWORK_CONNECTION if destination else EventType.PROCESS_EXECUTION,
        occurred_at=NOW + timedelta(minutes=minute),
        pid=pid,
        ppid=ppid,
        process_name=process_name,
        file_path=None,
        remote_domain=destination,
        http_host=None,
        tls_sni=None,
        remote_ip=None,
        dns_query=None,
        l7_protocol="HTTPS" if destination else None,
        protocol="TCP" if destination else None,
    )


class IncidentRows:
    def __init__(self, alerts: list[dict], incident: dict | None = None) -> None:
        self.alerts = alerts
        self.incident = _incident() if incident is None else incident

    def detail(self, _incident_id: int) -> dict | None:
        return self.incident

    def alerts_for_incident(self, _incident_id: int) -> list[dict]:
        return list(self.alerts)


class EventRows:
    def __init__(self, events: list[SimpleNamespace] | None = None, archive_ids: set[str] | None = None) -> None:
        self.events = {event.event_id: event for event in events or []}
        self.archive_ids = archive_ids or set()

    def detail(self, *, event_id: UUID, endpoint_id: int, occurred_at: datetime):
        assert endpoint_id == 1
        assert occurred_at.tzinfo is UTC
        rendered = str(event_id)
        if rendered in self.archive_ids:
            raise ApplicationError(409, "ARCHIVE_NOT_READY", "Archive is not ready.")
        return self.events.get(rendered)


def _service(incidents: IncidentRows, events: EventRows) -> InvestigationService:
    return InvestigationService(
        endpoints=SimpleNamespace(),
        alerts=SimpleNamespace(),
        incidents=incidents,
        events=events,
    )


def test_investigation_is_deterministic_and_every_edge_is_traceable() -> None:
    event_a_id = "018ff8f4-86de-7b25-9b8a-2d22f6a3b001"
    event_b_id = "018ff8f4-86de-7b25-9b8a-2d22f6a3b002"
    alerts = [_alert(2, event_a_id, minute=2), _alert(1, event_b_id, minute=1)]
    events = [
        _event(event_a_id, minute=2, pid=20, ppid=10, process_name="curl.exe", destination="c2.example"),
        _event(event_b_id, minute=1, pid=10, ppid=4, process_name="powershell.exe"),
    ]
    service = _service(IncidentRows(alerts), EventRows(events))

    first = service.investigation(7)
    second = service.investigation(7)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.partial is False
    assert first.truncated is False
    assert first.node_count == len(first.nodes) == 9
    assert first.edge_count == len(first.edges) == 9
    assert [node.node_type for node in first.nodes] == sorted(
        [node.node_type for node in first.nodes],
        key={
            InvestigationNodeType.INCIDENT: 0,
            InvestigationNodeType.ALERT: 1,
            InvestigationNodeType.EVENT: 2,
            InvestigationNodeType.PROCESS: 3,
            InvestigationNodeType.DESTINATION: 4,
        }.get,
    )
    assert {edge.relation for edge in first.edges} == set(InvestigationRelation)
    node_ids = {node.node_id for node in first.nodes}
    for edge in first.edges:
        assert edge.evidence is InvestigationEvidence.OBSERVED
        assert edge.source_node_id in node_ids
        assert edge.target_node_id in node_ids
        assert edge.incident_id == 7
        assert edge.event_id is not None


def test_missing_and_archive_events_return_partial_graph_without_fake_relations() -> None:
    missing_id = "018ff8f4-86de-7b25-9b8a-2d22f6a3c001"
    archive_id = "018ff8f4-86de-7b25-9b8a-2d22f6a3c002"
    result = _service(
        IncidentRows([_alert(1, missing_id, minute=1), _alert(2, archive_id, minute=2)]),
        EventRows(archive_ids={archive_id}),
    ).investigation(8)

    assert result.partial is True
    assert result.truncated is False
    assert [warning.code for warning in result.warnings] == [
        InvestigationWarningCode.ARCHIVE_NOT_READY,
        InvestigationWarningCode.EVENT_NOT_FOUND,
    ]
    assert result.fallback.timeline_available is True
    assert result.fallback.alert_table_available is True
    assert result.fallback.event_table_available is False
    assert {node.node_type for node in result.nodes} == {
        InvestigationNodeType.INCIDENT,
        InvestigationNodeType.ALERT,
    }
    assert {edge.relation for edge in result.edges} == {InvestigationRelation.CONTAINS}


def test_investigation_returns_not_found_for_missing_incident() -> None:
    service = _service(IncidentRows([], incident={}), EventRows())
    service.incidents.incident = None

    with pytest.raises(ApplicationError) as raised:
        service.investigation(999)

    assert raised.value.status_code == 404
    assert raised.value.code == "NOT_FOUND"


def test_oversized_graph_is_capped_without_dangling_edges() -> None:
    alerts = [_alert(index, str(UUID(int=index)), minute=1) for index in range(1, 261)]

    result = _service(IncidentRows(alerts), EventRows()).investigation(9)

    assert result.truncated is True
    assert result.node_count == len(result.nodes) == MAX_INVESTIGATION_NODES
    assert result.edge_count <= MAX_INVESTIGATION_EDGES
    assert len(result.warnings) == 260
    node_ids = {node.node_id for node in result.nodes}
    assert all(edge.source_node_id in node_ids and edge.target_node_id in node_ids for edge in result.edges)
