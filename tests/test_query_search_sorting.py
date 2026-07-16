from datetime import UTC, datetime, timedelta
from typing import Any

from backend.api_services import AlertService, EndpointService
from backend.contracts.enums import AlertSortBy
from backend.contracts.requests import AlertListQuery, EndpointListQuery
from backend.storage.postgres import AlertRepository, EndpointRepository, _alert_order_by

NOW = datetime(2026, 7, 15, 12, tzinfo=UTC)


def _endpoint_row(
    endpoint_id: int,
    *,
    hostname: str,
    agent_id: str,
    status: str,
    risk_score: int,
) -> dict[str, Any]:
    return {
        "endpoint_id": endpoint_id,
        "agent_id": agent_id,
        "hostname": hostname,
        "os_type": "WINDOWS",
        "os_version": None,
        "ip_address": None,
        "agent_version": None,
        "agent_build_id": None,
        "agent_arch": None,
        "capability_codes_json": [],
        "sensor_health_json": [],
        "registered_at": NOW - timedelta(days=endpoint_id),
        "status": status,
        "last_seen_at": NOW,
        "active_alerts": [
            {
                "alert_id": endpoint_id,
                "rule_code": f"RULE_{endpoint_id}",
                "rule_version": 1,
                "risk_score": risk_score,
                "detected_at": NOW,
                "title": f"Alert {endpoint_id}",
            }
        ],
        "open_incidents": [],
    }


class EndpointRows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.arguments: dict[str, Any] = {}

    def risk_snapshot(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.arguments = kwargs
        return self.rows


def test_endpoint_search_ranking_and_pagination_are_global_and_stable() -> None:
    repository = EndpointRows(
        [
            _endpoint_row(2, hostname="SOC", agent_id="agent-2", status="RETIRED", risk_score=90),
            _endpoint_row(3, hostname="soc-west", agent_id="agent-3", status="ONLINE", risk_score=20),
            _endpoint_row(4, hostname="workstation-4", agent_id="SOC", status="ONLINE", risk_score=80),
            _endpoint_row(5, hostname="soc-east", agent_id="agent-5", status="ONLINE", risk_score=90),
        ]
    )

    page = EndpointService(repository).list(
        EndpointListQuery(q="soc", page=2, size=2, sort_by="lastSeenAt", sort_order="asc"),
        calculated_at=NOW,
    )

    assert repository.arguments["q"] == "soc"
    assert page.total == 4
    assert [item.endpoint_id for item in page.items] == [5, 3]


def test_endpoint_default_sort_uses_endpoint_id_ascending_tiebreak() -> None:
    repository = EndpointRows(
        [
            _endpoint_row(9, hostname="zeta", agent_id="agent-9", status="ONLINE", risk_score=50),
            _endpoint_row(7, hostname="eta", agent_id="agent-7", status="ONLINE", risk_score=50),
        ]
    )

    page = EndpointService(repository).list(EndpointListQuery(size=1), calculated_at=NOW)

    assert page.total == 2
    assert [item.endpoint_id for item in page.items] == [7]


class CapturingCursor:
    def __init__(self) -> None:
        self.query = ""
        self.parameters: tuple[Any, ...] = ()

    def __enter__(self) -> "CapturingCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, query: str, parameters: tuple[Any, ...]) -> None:
        self.query = query
        self.parameters = parameters

    def fetchall(self) -> list[Any]:
        return []


class CapturingConnection:
    def __init__(self) -> None:
        self.cursor_instance = CapturingCursor()

    def cursor(self, **_kwargs: Any) -> CapturingCursor:
        return self.cursor_instance


def test_endpoint_repository_escapes_wildcards_and_backslashes() -> None:
    connection = CapturingConnection()

    assert EndpointRepository(connection).risk_snapshot(q=r"OPS%_\HOST") == []

    assert "ESCAPE E'\\\\'" in connection.cursor_instance.query
    expected = r"ops\%\_\\host" + "%"
    assert connection.cursor_instance.parameters[-3:] == (expected, expected, expected)


def test_endpoint_repository_numeric_query_uses_endpoint_id_exact_match() -> None:
    connection = CapturingConnection()

    EndpointRepository(connection).risk_snapshot(q="0007")

    assert connection.cursor_instance.parameters[-5:-3] == (7, 7)
    assert connection.cursor_instance.parameters[-3:] == (None, None, None)


def test_alert_ordering_contract_uses_global_priority_and_stable_tiebreak() -> None:
    priority = _alert_order_by(AlertSortBy.PRIORITY, "asc")

    assert priority == _alert_order_by(AlertSortBy.PRIORITY, "desc")
    assert priority.endswith("risk_score DESC, detected_at DESC, alert_id ASC")
    for sort_by in AlertSortBy:
        assert _alert_order_by(sort_by, "asc").endswith("alert_id ASC")
        assert _alert_order_by(sort_by, "desc").endswith("alert_id ASC")


def test_alert_service_passes_allowed_sort_to_repository() -> None:
    class Rows:
        arguments: dict[str, Any]

        def list_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
            self.arguments = kwargs
            return []

    repository = Rows()
    query = AlertListQuery.model_validate({"sortBy": "status", "sortOrder": "asc"})

    result = AlertService(repository, event_service=object(), rules=[]).list(
        query,
        from_=NOW - timedelta(days=1),
        to=NOW,
    )

    assert result.total == 0
    assert repository.arguments["sort_by"] is AlertSortBy.STATUS
    assert repository.arguments["sort_order"] == "asc"


def test_alert_repository_embeds_requested_order_before_fetching_rows() -> None:
    connection = CapturingConnection()

    AlertRepository(connection).list_rows(
        from_=NOW - timedelta(days=1),
        to=NOW,
        sort_by=AlertSortBy.SEVERITY,
        sort_order="desc",
    )

    assert "CASE severity" in connection.cursor_instance.query
    assert "DESC, alert_id ASC" in connection.cursor_instance.query
