from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.contracts.enums import EventType
from backend.contracts.requests import FailureListQuery
from backend.errors import ApplicationError, ServiceUnavailableError
from backend.investigation_service import FailureService, InvestigationService
from backend.storage.clickhouse import FailureRepository
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
    def __init__(self) -> None:
        self.calls = []

    def current_rows(self, **filters):
        self.calls.append(("rows", filters))
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

    def count_current(self, **filters):
        self.calls.append(("count", filters))
        return 12


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
    repository = FailureRepositoryFake()
    query = FailureListQuery.model_validate({"timePreset": "LATEST_24H", "page": 2, "size": 5})
    page = FailureService(repository).list(query, from_=NOW, to=NOW.replace(hour=4))
    assert page.total == 12
    assert UUID(page.items[0].failure_id)
    assert page.items[0].failed_at.tzinfo is UTC
    assert repository.calls[0][1]["limit"] == 5
    assert repository.calls[0][1]["offset"] == 5
    assert "limit" not in repository.calls[1][1]


def test_failure_repository_pages_and_counts_current_rows_in_clickhouse() -> None:
    calls = []

    class Client:
        def query(self, query, parameters=None):
            normalized = " ".join(query.split())
            calls.append((normalized, parameters))
            return SimpleNamespace(result_rows=[(9,)] if normalized.startswith("SELECT uniqExact") else [])

    repository = FailureRepository(Client())
    assert repository.current_rows(status="FAILED", limit=10, offset=20) == []
    assert repository.count_current(status="FAILED") == 9
    assert "LIMIT {limit:UInt64} OFFSET {offset:UInt64}" in calls[0][0]
    assert calls[0][1]["limit"] == 10
    assert calls[0][1]["offset"] == 20
    assert "uniqExact(failure_id)" in calls[1][0]


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
        alerts_for_incident=lambda _incident_id, **_filters: [{
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


def test_attack_timeline_does_not_hide_infrastructure_failure() -> None:
    event_id = str(uuid4())
    incidents = SimpleNamespace(
        detail=lambda _incident_id: {
            "endpoint_id": 1,
            "first_detected_at": NOW,
            "title": "Incident",
            "description": None,
            "severity": "HIGH",
        },
        alerts_for_incident=lambda _incident_id, **_filters: [
            {
                "event_id": event_id,
                "event_occurred_at": NOW,
                "detected_at": NOW,
                "title": "Alert",
                "summary": "Summary",
                "severity": "HIGH",
                "alert_id": 9,
            }
        ],
    )
    events = SimpleNamespace(
        detail=lambda **_identity: (_ for _ in ()).throw(ServiceUnavailableError("archive unavailable"))
    )
    service = InvestigationService(
        endpoints=SimpleNamespace(), alerts=SimpleNamespace(), incidents=incidents, events=events
    )

    with pytest.raises(ServiceUnavailableError):
        service.timeline(3)


def test_topology_rejects_oversized_event_range_and_pushes_single_endpoint_filter() -> None:
    calls = []

    class TooManyEvents:
        def list_rows(self, query, *, from_, to):
            calls.append(query.endpoint_id)
            return [], 10_001

    service = InvestigationService(
        endpoints=SimpleNamespace(),
        alerts=SimpleNamespace(),
        incidents=SimpleNamespace(),
        events=TooManyEvents(),
    )

    with pytest.raises(ApplicationError, match="narrow the time range") as caught:
        service.topology(from_=NOW, to=NOW.replace(hour=4), endpoint_ids=[7], calculated_at=NOW)

    assert caught.value.status_code == 400
    assert calls == [7]


def test_topology_queries_each_selected_endpoint_instead_of_loading_global_events() -> None:
    calls = []

    class EmptyEvents:
        def list_rows(self, query, *, from_, to):
            calls.append(query.endpoint_id)
            return [], 0

    service = InvestigationService(
        endpoints=SimpleNamespace(risk_snapshot=lambda **_filters: []),
        alerts=SimpleNamespace(list_rows=lambda **_filters: []),
        incidents=SimpleNamespace(),
        events=EmptyEvents(),
    )

    topology = service.topology(from_=NOW, to=NOW.replace(hour=4), endpoint_ids=[8, 7], calculated_at=NOW)

    assert topology.nodes == []
    assert topology.edges == []
    assert calls == [7, 8]


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


def test_ingest_summary_scopes_events_failures_and_storage_to_endpoint() -> None:
    event_calls: list[dict[str, object]] = []
    failure_calls: list[dict[str, object]] = []

    def ingest_summary(**filters):
        event_calls.append(filters)
        return (7, NOW)

    def current_rows(**filters):
        failure_calls.append(filters)
        return [{"status": "FAILED", "failed_at": NOW}]

    storage = [
        {"endpoint_id": 1, "storage_backend": "S3", "storage_status": "RESTORED"},
        {"endpoint_id": 2, "storage_backend": "S3", "storage_status": "RESTORED"},
    ]
    service = SummaryService(
        endpoints=SimpleNamespace(),
        alerts=SimpleNamespace(),
        incidents=SimpleNamespace(),
        metadata=SimpleNamespace(all_current=lambda: storage),
        events=SimpleNamespace(ingest_summary=ingest_summary),
        failures=SimpleNamespace(current_rows=current_rows),
        event_service=SimpleNamespace(),
    )

    summary = service.ingest_summary(from_=NOW, to=NOW.replace(hour=4), endpoint_id=2)

    assert event_calls == [{"from_": NOW, "to": NOW.replace(hour=4), "endpoint_id": 2}]
    assert failure_calls == [{"from_": NOW, "to": NOW.replace(hour=4), "endpoint_id": 2}]
    assert summary.events.ingested_count == 7
    assert summary.storage.restored_bucket_count == 1
