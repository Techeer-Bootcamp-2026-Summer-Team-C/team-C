from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from backend.contracts.enums import EventType
from backend.contracts.requests import FailureListQuery
from backend.investigation_service import FailureService, InvestigationService
from backend.summary_service import SummaryService

NOW = datetime(2026, 7, 14, 3, tzinfo=UTC)


class EventServiceFake:
    def __init__(self, items):
        self.items = items

    def list_rows(self, _query, *, from_, to):
        return list(self.items), len(self.items)

    def detail(self, *, event_id, endpoint_id, occurred_at):
        return next((item for item in self.items if item.event_id == str(event_id)), None)


class FailureRepositoryFake:
    def current_rows(self, **_filters):
        return [{
            "failure_id": uuid4(), "event_id": uuid4(), "endpoint_id": 1,
            "source_topic": "telemetry", "source_partition": 0, "source_offset": 7,
            "consumer_name": "detection", "failure_stage": "rule-evaluation", "failure_code": "RULE_ERROR",
            "error_message": "bad rule", "retryable": True, "retry_count": 1,
            "payload_object_key": None, "payload_sha256": None, "payload_size_bytes": None, "status": "FAILED",
            "failed_at": NOW.replace(tzinfo=None), "replay_count": 0, "last_replayed_at": None,
            "reprocess_outcome": None, "resolved_at": None,
            "retention_expires_at": NOW.replace(tzinfo=None),
            "created_at": NOW.replace(tzinfo=None), "updated_at": NOW.replace(tzinfo=None),
        }]


def process_event(pid: int, ppid: int | None, minute: int):
    return SimpleNamespace(
        event_id=str(uuid4()), endpoint_id=1, event_type=EventType.PROCESS_EXECUTION,
        pid=pid, ppid=ppid, process_name=f"proc-{pid}", process_path=None,
        command_line=f"proc-{pid}.exe", user_name="tester", occurred_at=NOW.replace(minute=minute),
    )


def test_process_tree_groups_pid_rows_and_marks_selected_parent() -> None:
    service = InvestigationService(
        endpoints=SimpleNamespace(), alerts=SimpleNamespace(), incidents=SimpleNamespace(),
        events=EventServiceFake([process_event(10, None, 0), process_event(20, 10, 1), process_event(20, 10, 2)]),
    )
    tree = service.process_tree(1, from_=NOW.replace(minute=0), to=NOW.replace(minute=30), selected_pid=20)
    assert [(node.pid, node.event_count, node.selected, node.parent_captured) for node in tree.nodes] == [
        (10, 1, False, False), (20, 2, True, True),
    ]


def test_failure_service_converts_clickhouse_uuid_and_naive_timestamps() -> None:
    query = FailureListQuery.model_validate({"timePreset": "LATEST_24H", "page": 1, "size": 50})
    page = FailureService(FailureRepositoryFake()).list(query, from_=NOW, to=NOW.replace(hour=4))
    assert page.total == 1
    assert UUID(page.items[0].failure_id)
    assert page.items[0].failed_at.tzinfo is UTC


def test_attack_timeline_orders_incident_event_and_alert() -> None:
    event_id = str(uuid4())
    event = SimpleNamespace(
        event_id=event_id, endpoint_id=1, event_type=EventType.NETWORK_CONNECTION,
        occurred_at=NOW.replace(minute=1), process_name="powershell.exe", remote_domain="example.test",
        remote_ip="203.0.113.2", file_path=None, command_line="powershell -enc ...", dns_query=None, http_host=None,
    )
    incidents = SimpleNamespace(
        detail=lambda _incident_id: {
            "endpoint_id": 1, "first_detected_at": NOW, "title": "Encoded command chain",
            "description": "Correlated detection", "severity": "HIGH",
        },
        alerts_for_incident=lambda _incident_id: [{
            "event_id": event_id, "event_occurred_at": event.occurred_at,
            "detected_at": NOW.replace(minute=2), "title": "Encoded PowerShell",
            "summary": "Matched encoded command", "severity": "HIGH", "alert_id": 9,
        }],
    )
    service = InvestigationService(
        endpoints=SimpleNamespace(), alerts=SimpleNamespace(), incidents=incidents, events=EventServiceFake([event]),
    )
    timeline = service.timeline(3)
    assert [item.item_type for item in timeline.items] == ["INCIDENT", "EVENT", "ALERT"]
    assert timeline.items[1].event_id == event_id


def test_ingest_summary_calculates_event_and_failure_rates() -> None:
    events = SimpleNamespace(ingest_summary=lambda **_range: (120, NOW))
    failures = SimpleNamespace(current_rows=lambda **_range: [
        {"status": "FAILED", "failed_at": NOW}, {"status": "REPROCESSED", "failed_at": NOW},
    ])
    service = SummaryService(
        endpoints=SimpleNamespace(), alerts=SimpleNamespace(), incidents=SimpleNamespace(),
        metadata=SimpleNamespace(all_current=lambda: []), events=events, failures=failures,
        event_service=SimpleNamespace(),
    )
    summary = service.ingest_summary(from_=NOW, to=NOW.replace(hour=4))
    assert summary.events.rate_per_minute == 2
    assert summary.event_failures.rate_per_minute == 2 / 60
