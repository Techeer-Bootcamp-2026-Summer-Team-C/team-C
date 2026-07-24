from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.api_services import AlertService, IncidentService
from backend.contracts.enums import AlertStatus, IncidentStatus
from backend.contracts.events import EventDto
from backend.errors import ApplicationError
from backend.storage.postgres import IncidentRepository

NOW = datetime(2026, 7, 25, tzinfo=UTC)


def test_resolved_alert_can_be_reopened_without_losing_its_identity() -> None:
    class Repository:
        def update_status_with_audit(self, **kwargs):
            assert kwargs["status"] is AlertStatus.OPEN
            return alert_row(status="OPEN", updated_at=kwargs["changed_at"])

    result = AlertService(Repository(), event_service=object(), rules=[]).update_status(
        11,
        status=AlertStatus.OPEN,
        actor_identifier="7",
        request_id="req-alert-reopen",
        changed_at=NOW,
    )

    assert result.alert_id == 11
    assert result.event_id == "018ff8f4-86de-7b25-9b8a-2d22f6a3e001"
    assert result.status is AlertStatus.OPEN


def test_closed_incident_can_be_reopened_through_the_status_service() -> None:
    class Repository:
        arguments: dict

        def update_status_with_audit(self, **kwargs):
            self.arguments = kwargs
            return incident_row(status="OPEN", closed_at=None, updated_at=kwargs["changed_at"])

    repository = Repository()
    result = IncidentService(repository).update_status(
        21,
        status=IncidentStatus.OPEN,
        actor_identifier="7",
        request_id="req-incident-reopen",
        changed_at=NOW,
    )

    assert result.incident_id == 21
    assert result.status is IncidentStatus.OPEN
    assert result.closed_at is None
    assert repository.arguments["actor_identifier"] == "7"
    assert repository.arguments["request_id"] == "req-incident-reopen"


def test_missing_incident_status_update_is_reported_as_not_found() -> None:
    repository = SimpleNamespace(
        update_status_with_audit=lambda **_kwargs: (_ for _ in ()).throw(KeyError(999))
    )

    with pytest.raises(ApplicationError) as caught:
        IncidentService(repository).update_status(
            999,
            status=IncidentStatus.OPEN,
            actor_identifier="7",
            request_id="req-missing-incident",
            changed_at=NOW,
        )

    assert caught.value.status_code == 404
    assert caught.value.code == "NOT_FOUND"


def test_automatic_incident_close_skips_manually_overridden_statuses() -> None:
    class Connection:
        def __init__(self) -> None:
            self.query = ""
            self.parameters = ()

        def transaction(self):
            return nullcontext()

        def execute(self, query, parameters):
            self.query = " ".join(query.split())
            self.parameters = parameters
            return SimpleNamespace(rowcount=3)

    connection = Connection()

    assert IncidentRepository(connection).close_expired(NOW) == 3
    assert "status_overridden = FALSE" in connection.query
    assert connection.parameters == (NOW, NOW)


def test_events_remain_read_only_evidence_without_a_mutable_status_field() -> None:
    assert "status" not in EventDto.model_fields


def alert_row(*, status: str, updated_at: datetime) -> dict:
    return {
        "alert_id": 11,
        "endpoint_id": 1,
        "event_id": UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3e001"),
        "event_occurred_at": NOW - timedelta(minutes=2),
        "batch_id": None,
        "agent_id": "agent-1",
        "rule_code": "PROC-001",
        "rule_name": "Suspicious process",
        "rule_version": 1,
        "mitre_tactic_code": "TA0002",
        "mitre_tactic_name": "Execution",
        "mitre_technique_code": "T1059",
        "mitre_technique_name": "Command and Scripting Interpreter",
        "title": "Suspicious process",
        "summary": "Suspicious process activity",
        "severity": "HIGH",
        "risk_score": Decimal("85"),
        "status": status,
        "detected_at": NOW - timedelta(minutes=1),
        "created_at": NOW - timedelta(minutes=1),
        "updated_at": updated_at,
    }


def incident_row(*, status: str, closed_at: datetime | None, updated_at: datetime) -> dict:
    return {
        "incident_id": 21,
        "endpoint_id": 1,
        "correlation_key": "endpoint:1:proc",
        "window_start_at": NOW - timedelta(hours=1),
        "window_end_at": NOW - timedelta(minutes=30),
        "title": "Suspicious process chain",
        "description": "Correlated evidence",
        "severity": "HIGH",
        "status": status,
        "first_detected_at": NOW - timedelta(hours=1),
        "last_detected_at": NOW - timedelta(minutes=45),
        "closed_at": closed_at,
        "created_at": NOW - timedelta(hours=1),
        "updated_at": updated_at,
        "alert_count": 2,
    }
