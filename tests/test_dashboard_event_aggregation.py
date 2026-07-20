from collections import Counter
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import backend.event_service as event_service_module
from backend.event_service import EventService
from backend.storage.clickhouse import DASHBOARD_TOP_LIMIT, DashboardEventAggregate, EventRepository

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)


class RecordingClient:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, object]]] = []

    def query(self, query: str, parameters: dict[str, object] | None = None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, dict(parameters or {})))
        if normalized.startswith("SELECT event_type, toStartOfInterval"):
            rows = [
                ("PROCESS_EXECUTION", NOW, 4),
                ("PROCESS_EXECUTION", NOW + timedelta(hours=1), 3),
                ("DNS_QUERY", NOW + timedelta(hours=1), 5),
            ]
        elif "ARRAY JOIN" in normalized:
            rows = [
                ("top_processes", "powershell.exe", 7),
                ("top_remote_ips", "203.0.113.10", 4),
                ("top_domains", "example.test", 6),
                ("top_file_hashes", "a" * 64, 3),
                ("top_dns_queries", "example.test", 5),
                ("top_l7_protocols", "HTTPS", 2),
            ]
        else:
            raise AssertionError(f"unexpected query: {normalized}")
        return SimpleNamespace(result_rows=rows)


def test_dashboard_summary_aggregates_in_clickhouse_without_raw_event_projection() -> None:
    client = RecordingClient()

    result = EventRepository(client).dashboard_summary(
        from_=NOW,
        to=NOW + timedelta(days=1),
        interval_seconds=3600,
        endpoint_id=7,
    )

    assert result.total_count == 12
    assert result.by_event_type == {"PROCESS_EXECUTION": 7, "DNS_QUERY": 5}
    assert result.top_processes == {"powershell.exe": 7}
    assert result.top_domains == {"example.test": 6}
    assert result.time_series == {NOW: 4, NOW + timedelta(hours=1): 8}
    assert len(client.queries) == 2
    assert all("raw_payload" not in query for query, _parameters in client.queries)
    assert all(parameters["endpoint_id"] == 7 for _query, parameters in client.queries)
    assert f"LIMIT {DASHBOARD_TOP_LIMIT} BY target" in client.queries[1][0]


def test_dashboard_summary_rejects_an_unknown_interval_before_querying() -> None:
    client = RecordingClient()

    with pytest.raises(ValueError, match="unsupported dashboard interval"):
        EventRepository(client).dashboard_summary(
            from_=NOW,
            to=NOW + timedelta(days=1),
            interval_seconds=30,
        )

    assert client.queries == []


def test_event_service_merges_restored_events_into_clickhouse_aggregate() -> None:
    clickhouse_aggregate = DashboardEventAggregate(
        total_count=1,
        by_event_type=Counter({"PROCESS_EXECUTION": 1}),
        top_processes=Counter({"powershell.exe": 1}),
        time_series=Counter({NOW: 1}),
    )
    events = SimpleNamespace(dashboard_summary=lambda **_filters: clickhouse_aggregate)
    metadata = SimpleNamespace(
        overlapping_all=lambda **_filters: [
            {
                "endpoint_id": 2,
                "bucket_start_at": NOW,
                "storage_backend": "S3",
                "storage_status": "RESTORED",
                "storage_path": "restored/endpoint-2.parquet",
            }
        ]
    )
    restored_event = {
        "event_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3a002",
        "endpoint_id": 2,
        "event_type": "DNS_QUERY",
        "occurred_at": NOW + timedelta(minutes=5),
        "process_name": "chrome.exe",
        "remote_ip": "203.0.113.20",
        "remote_domain": "restored.example.test",
        "http_host": None,
        "file_hash_sha256": None,
        "dns_query": "restored.example.test",
        "l7_protocol": None,
    }
    restored = SimpleNamespace(read_rows=lambda _path, **_filters: [restored_event, restored_event])

    result = EventService(events=events, metadata=metadata, restored=restored).dashboard_summary(
        from_=NOW,
        to=NOW + timedelta(hours=1),
        interval_seconds=3600,
    )

    assert result.total_count == 2
    assert result.by_event_type == {"PROCESS_EXECUTION": 1, "DNS_QUERY": 1}
    assert result.top_processes == {"powershell.exe": 1, "chrome.exe": 1}
    assert result.top_domains == {"restored.example.test": 1}
    assert result.time_series == {NOW: 2}


def test_restored_dashboard_rejects_metadata_count_above_hard_limit(monkeypatch) -> None:
    monkeypatch.setattr(event_service_module, "MAX_RESTORED_DASHBOARD_EVENTS", 1)
    metadata = SimpleNamespace(
        overlapping_all=lambda **_filters: [
            {
                "endpoint_id": 2,
                "bucket_start_at": NOW,
                "storage_backend": "S3",
                "storage_status": "RESTORED",
                "storage_path": "restored/endpoint-2.parquet",
                "event_count": 2,
            }
        ]
    )
    service = EventService(
        events=SimpleNamespace(dashboard_summary=lambda **_filters: DashboardEventAggregate()),
        metadata=metadata,
        restored=SimpleNamespace(read_rows=lambda *_args, **_filters: pytest.fail("scan must be rejected")),
    )

    with pytest.raises(Exception, match="too large"):
        service.dashboard_summary(from_=NOW, to=NOW + timedelta(hours=1), interval_seconds=3600)
