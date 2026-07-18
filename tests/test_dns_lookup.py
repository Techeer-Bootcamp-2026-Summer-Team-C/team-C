from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend.dns_service as dns_service_module
from backend import dns_lookup
from backend.dns_lookup import DnsLookupError, forward_lookup, normalize_domain, resolve_record, reverse_lookup
from backend.dns_service import DnsIntelligenceService
from backend.errors import ApplicationError
from backend.main import create_app
from backend.storage.clickhouse import EventRepository

FROM = datetime(2026, 1, 1, tzinfo=UTC)
TO = datetime(2026, 1, 2, tzinfo=UTC)


class FakeEventRepository:
    """Stands in for EventRepository: returns canned rows keyed by the active filter and,
    like the real ClickHouse query, applies endpoint_ids scoping itself (DB-side)."""

    def __init__(self, rows_by_filter: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_filter = rows_by_filter

    def search(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
        endpoint_ids: list[int] | None = None,
        event_type: str | None = None,
        process_name: str | None = None,
        file_path: str | None = None,
        domain: str | None = None,
        related_domain: str | None = None,
        remote_ip: str | None = None,
        dns_query: str | None = None,
        dns_answer_ip: str | None = None,
        l7_protocol: str | None = None,
        columns: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if remote_ip is not None:
            rows = self.rows_by_filter.get("remote_ip", [])
        elif dns_answer_ip is not None:
            rows = self.rows_by_filter.get("dns_answer_ip", [])
        elif related_domain is not None:
            rows = self.rows_by_filter.get("related_domain", [])
        else:
            rows = []
        if endpoint_ids:
            allowed = set(endpoint_ids)
            rows = [row for row in rows if row.get("endpoint_id") in allowed]
        if columns is not None:
            rows = [{column: row.get(column) for column in columns} for row in rows]
        return rows[:limit] if limit is not None else rows


class RecordingClient:
    """Captures the SQL/parameters EventRepository builds, without a real ClickHouse."""

    def __init__(self) -> None:
        self.last_query: str | None = None
        self.last_parameters: dict[str, Any] | None = None

    def query(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
        self.last_query = query
        self.last_parameters = parameters
        return SimpleNamespace(result_rows=[])


def _make_resolver(mapping: dict[str, Any]):
    def _resolve(domain: str, record_type: str, *, timeout: float = 3.0) -> list[str]:
        result = mapping[record_type]
        if isinstance(result, DnsLookupError):
            raise result
        return result

    return _resolve


# --- normalize_domain / validation -----------------------------------------


def test_normalize_domain_trims_lowercases_and_strips_trailing_dot() -> None:
    assert normalize_domain("  Example.COM.  ") == "example.com"
    assert normalize_domain("DNS.Google.") == "dns.google"


def test_normalize_domain_rejects_empty_label() -> None:
    with pytest.raises(DnsLookupError) as error:
        normalize_domain("bad..name")
    assert error.value.code == "INVALID_DOMAIN"


def test_normalize_domain_rejects_too_long_label() -> None:
    with pytest.raises(DnsLookupError) as error:
        normalize_domain("a" * 64 + ".com")
    assert error.value.code == "INVALID_DOMAIN"


def test_resolve_record_rejects_unsupported_type() -> None:
    with pytest.raises(DnsLookupError) as error:
        resolve_record("example.com", "TXT")
    assert error.value.code == "UNSUPPORTED_RECORD_TYPE"


def test_reverse_lookup_rejects_invalid_ip() -> None:
    with pytest.raises(DnsLookupError) as error:
        reverse_lookup("not-an-ip")
    assert error.value.code == "INVALID_IP"


# --- forward_lookup error preservation (resolver stubbed) ------------------


def test_forward_lookup_preserves_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dns_lookup,
        "resolve_record",
        _make_resolver({"A": DnsLookupError("TIMEOUT", "a"), "AAAA": DnsLookupError("TIMEOUT", "aaaa")}),
    )
    with pytest.raises(DnsLookupError) as error:
        forward_lookup("example.com")
    assert error.value.code == "TIMEOUT"


def test_forward_lookup_preserves_no_nameservers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dns_lookup,
        "resolve_record",
        _make_resolver(
            {"A": DnsLookupError("NO_NAMESERVERS", "a"), "AAAA": DnsLookupError("NO_NAMESERVERS", "aaaa")}
        ),
    )
    with pytest.raises(DnsLookupError) as error:
        forward_lookup("example.com")
    assert error.value.code == "NO_NAMESERVERS"


def test_forward_lookup_reports_no_answer_when_records_only_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dns_lookup,
        "resolve_record",
        _make_resolver({"A": DnsLookupError("NO_ANSWER", "a"), "AAAA": DnsLookupError("NO_ANSWER", "aaaa")}),
    )
    with pytest.raises(DnsLookupError) as error:
        forward_lookup("example.com")
    assert error.value.code == "NO_ANSWER"


def test_forward_lookup_succeeds_when_any_record_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dns_lookup,
        "resolve_record",
        _make_resolver({"A": ["1.2.3.4"], "AAAA": DnsLookupError("NO_ANSWER", "aaaa")}),
    )
    assert forward_lookup("example.com") == ["1.2.3.4"]


def test_forward_lookup_prefers_infrastructure_error_over_no_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dns_lookup,
        "resolve_record",
        _make_resolver({"A": DnsLookupError("TIMEOUT", "a"), "AAAA": DnsLookupError("NO_ANSWER", "aaaa")}),
    )
    with pytest.raises(DnsLookupError) as error:
        forward_lookup("example.com")
    assert error.value.code == "TIMEOUT"


# --- SQL construction: boundary, JSON membership, endpoint pushdown --------


def test_related_domain_uses_exact_and_subdomain_boundary_not_substring() -> None:
    client = RecordingClient()
    EventRepository(client).search(from_=FROM, to=TO, related_domain="yahoo.com")
    query = client.last_query or ""
    assert "= lowerUTF8({related_domain:String})" in query
    assert "endsWith(lowerUTF8(ifNull(remote_domain, '')), lowerUTF8(concat('.', {related_domain:String})))" in query
    assert "dns_query" in query and "tls_sni" in query and "http_host" in query
    assert "positionCaseInsensitiveUTF8(ifNull(remote_domain, ''), {related_domain:String})" not in query


def test_dns_answer_ip_uses_json_array_membership_not_quoted_substring() -> None:
    client = RecordingClient()
    EventRepository(client).search(from_=FROM, to=TO, dns_answer_ip="1.2.3.4")
    query = client.last_query or ""
    assert "has(JSONExtract(ifNull(dns_answers_json, '[]'), 'Array(String)'), {dns_answer_ip:String})" in query
    assert "concat('\"'" not in query


def test_search_pushes_endpoint_ids_into_sql() -> None:
    client = RecordingClient()
    EventRepository(client).search(from_=FROM, to=TO, endpoint_ids=[1, 2], remote_ip="8.8.8.8")
    query = client.last_query or ""
    assert "endpoint_id IN {endpoint_ids:Array(UInt64)}" in query
    assert client.last_parameters is not None and client.last_parameters["endpoint_ids"] == [1, 2]


def test_events_ui_domain_filter_keeps_substring_matching() -> None:
    client = RecordingClient()
    EventRepository(client).search(from_=FROM, to=TO, domain="yahoo")
    query = client.last_query or ""
    assert "positionCaseInsensitiveUTF8(ifNull(remote_domain, ''), {domain:String})" in query


def test_event_search_applies_stable_database_pagination() -> None:
    client = RecordingClient()

    EventRepository(client).search(from_=FROM, to=TO, sort_order="desc", limit=50, offset=100)

    query = client.last_query or ""
    assert "ORDER BY occurred_at DESC, event_id DESC" in query
    assert "LIMIT {limit:UInt64} OFFSET {offset:UInt64}" in query
    assert client.last_parameters is not None
    assert client.last_parameters["limit"] == 50
    assert client.last_parameters["offset"] == 100


def test_event_search_projection_does_not_fetch_raw_payload() -> None:
    client = RecordingClient()

    EventRepository(client).search(
        from_=FROM,
        to=TO,
        related_domain="example.com",
        columns=["remote_domain", "remote_ip"],
        limit=10,
    )

    query = client.last_query or ""
    assert query.startswith("SELECT remote_domain, remote_ip")
    assert "raw_payload" not in query


def test_event_count_uses_distinct_event_identity() -> None:
    class CountClient(RecordingClient):
        def query(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
            self.last_query = query
            self.last_parameters = parameters
            return SimpleNamespace(result_rows=[(17,)])

    client = CountClient()

    assert EventRepository(client).count_search(from_=FROM, to=TO, endpoint_id=7) == 17
    assert "SELECT uniqExact(event_id)" in (client.last_query or "")


# --- Correlation logic (resolver stubbed; deterministic, no network) -------


def test_correlate_by_ip_combines_live_dns_and_observed_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.dns_service.reverse_lookup", lambda ip: ["dns.google"])
    events = FakeEventRepository(
        {
            "remote_ip": [
                {"endpoint_id": 1, "remote_domain": "observed.example.com", "http_host": None, "tls_sni": None}
            ],
            "dns_answer_ip": [{"endpoint_id": 1, "dns_query": "resolved-from-answers.example.com"}],
        }
    )
    result = DnsIntelligenceService(events=events).correlate("8.8.8.8", from_=FROM, to=TO)
    assert result.input_type == "IP"
    sources_by_value = {item.value: item.sources for item in result.related}
    assert sources_by_value["dns.google"] == ["LIVE_DNS"]
    assert sources_by_value["observed.example.com"] == ["OBSERVED_EVENTS"]
    assert sources_by_value["resolved-from-answers.example.com"] == ["OBSERVED_EVENTS"]
    assert {
        (edge.source_value, edge.target_value, edge.relation, tuple(edge.sources))
        for edge in result.relationships
    } == {
        ("8.8.8.8", "dns.google", "PTR_CANDIDATE", ("LIVE_DNS",)),
        ("observed.example.com", "8.8.8.8", "RESOLVES_TO", ("OBSERVED_EVENTS",)),
        ("resolved-from-answers.example.com", "8.8.8.8", "RESOLVES_TO", ("OBSERVED_EVENTS",)),
    }


def test_correlate_rejects_event_volume_above_hard_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dns_service_module, "MAX_CORRELATION_EVENTS", 2)
    monkeypatch.setattr("backend.dns_service.forward_lookup", lambda _domain: [])
    events = FakeEventRepository(
        {
            "related_domain": [
                {"remote_domain": "example.com", "remote_ip": f"203.0.113.{index}"}
                for index in range(1, 4)
            ]
        }
    )

    with pytest.raises(ApplicationError, match="narrow the time range"):
        DnsIntelligenceService(events=events).correlate("example.com", from_=FROM, to=TO)


def test_correlate_by_domain_combines_forward_dns_and_observed_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.dns_service.forward_lookup", lambda domain: ["198.51.100.5"])
    events = FakeEventRepository(
        {
            "related_domain": [
                {
                    "endpoint_id": 1,
                    "remote_domain": "mail.example.com",
                    "dns_query": "example.com",
                    "remote_ip": "203.0.113.10",
                    "dns_answers_json": '["203.0.113.10", "203.0.113.11"]',
                },
            ]
        }
    )
    result = DnsIntelligenceService(events=events).correlate("example.com", from_=FROM, to=TO)
    assert result.input_type == "DOMAIN"
    sources_by_value = {item.value: item.sources for item in result.related}
    assert sources_by_value["198.51.100.5"] == ["LIVE_DNS"]
    assert sources_by_value["203.0.113.10"] == ["OBSERVED_EVENTS"]
    assert sources_by_value["203.0.113.11"] == ["OBSERVED_EVENTS"]
    assert sources_by_value["mail.example.com"] == ["OBSERVED_EVENTS"]
    relationships = {(edge.source_value, edge.target_value, edge.relation) for edge in result.relationships}
    assert ("example.com", "198.51.100.5", "RESOLVES_TO") in relationships
    assert ("mail.example.com", "example.com", "SUBDOMAIN_OF") in relationships
    assert ("mail.example.com", "203.0.113.10", "RESOLVES_TO") in relationships
    assert ("example.com", "203.0.113.11", "RESOLVES_TO") in relationships


def test_correlate_keeps_observed_events_when_live_dns_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(ip: str) -> list[str]:
        raise DnsLookupError("TIMEOUT", "resolver unavailable")

    monkeypatch.setattr("backend.dns_service.reverse_lookup", _boom)
    events = FakeEventRepository({"remote_ip": [{"endpoint_id": 1, "remote_domain": "observed-only.example.com"}]})
    result = DnsIntelligenceService(events=events).correlate("203.0.113.99", from_=FROM, to=TO)
    assert result.input_type == "IP"
    assert [item.value for item in result.related] == ["observed-only.example.com"]
    assert result.related[0].sources == ["OBSERVED_EVENTS"]
    assert [(edge.source_value, edge.target_value, edge.relation) for edge in result.relationships] == [
        ("observed-only.example.com", "203.0.113.99", "RESOLVES_TO")
    ]


def test_correlate_normalizes_domain_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.dns_service.forward_lookup", lambda domain: [])
    events = FakeEventRepository({})
    # "Example.COM." must be treated identically to "example.com"
    result = DnsIntelligenceService(events=events).correlate("Example.COM.", from_=FROM, to=TO)
    assert result.input_value == "example.com"
    assert result.input_type == "DOMAIN"


def test_correlate_dedupes_case_and_trailing_dot_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    # "DNS.Google." and "dns.google" are the same host and must collapse to one entry.
    monkeypatch.setattr("backend.dns_service.reverse_lookup", lambda ip: ["DNS.Google.", "dns.google"])
    events = FakeEventRepository({})
    result = DnsIntelligenceService(events=events).correlate("8.8.8.8", from_=FROM, to=TO)
    assert [item.value for item in result.related] == ["dns.google"]


def test_correlate_dedupes_equivalent_ipv6_notations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.dns_service.forward_lookup", lambda domain: [])
    events = FakeEventRepository(
        {
            "related_domain": [
                {
                    "endpoint_id": 1,
                    "dns_query": "example.com",
                    "remote_ip": "2001:db8::1",
                    "dns_answers_json": '["2001:0db8:0000:0000:0000:0000:0000:0001"]',
                }
            ]
        }
    )
    result = DnsIntelligenceService(events=events).correlate("example.com", from_=FROM, to=TO)
    assert [item.value for item in result.related] == ["2001:db8::1"]


def test_correlate_merges_live_and_observed_sources_on_same_relationship(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.dns_service.forward_lookup", lambda domain: ["203.0.113.10"])
    events = FakeEventRepository(
        {
            "related_domain": [
                {
                    "endpoint_id": 1,
                    "remote_domain": "example.com",
                    "remote_ip": "203.0.113.10",
                }
            ]
        }
    )
    result = DnsIntelligenceService(events=events).correlate("example.com", from_=FROM, to=TO)
    assert len(result.relationships) == 1
    assert result.relationships[0].relation == "RESOLVES_TO"
    assert result.relationships[0].sources == ["LIVE_DNS", "OBSERVED_EVENTS"]


def test_correlate_only_builds_subdomain_edges_inside_requested_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.dns_service.forward_lookup", lambda domain: [])
    events = FakeEventRepository(
        {
            "related_domain": [
                {
                    "endpoint_id": 1,
                    "remote_domain": "mail.yahoo.com",
                    "http_host": "yahoo.com.evil.example",
                    "tls_sni": "notyahoo.com",
                    "remote_ip": "203.0.113.10",
                }
            ]
        }
    )
    result = DnsIntelligenceService(events=events).correlate("yahoo.com", from_=FROM, to=TO)
    assert [item.value for item in result.related] == ["203.0.113.10", "mail.yahoo.com"]
    assert {(edge.source_value, edge.target_value, edge.relation) for edge in result.relationships} == {
        ("mail.yahoo.com", "203.0.113.10", "RESOLVES_TO"),
        ("mail.yahoo.com", "yahoo.com", "SUBDOMAIN_OF"),
    }


def test_correlate_filters_by_endpoint_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.dns_service.reverse_lookup", lambda ip: [])
    events = FakeEventRepository(
        {
            "remote_ip": [
                {"endpoint_id": 1, "remote_domain": "ep1.example.com"},
                {"endpoint_id": 2, "remote_domain": "ep2.example.com"},
            ]
        }
    )
    result = DnsIntelligenceService(events=events).correlate("8.8.8.8", from_=FROM, to=TO, endpoint_ids=[1])
    assert [item.value for item in result.related] == ["ep1.example.com"]


@pytest.mark.parametrize("bad_value", ["bad..name", "a" * 64 + ".com"])
def test_correlate_rejects_invalid_domain_input(bad_value: str) -> None:
    events = FakeEventRepository({})
    with pytest.raises(ApplicationError) as error:
        DnsIntelligenceService(events=events).correlate(bad_value, from_=FROM, to=TO)
    assert error.value.status_code == 400


@pytest.mark.parametrize("bad_ip", ["1.2.3", "999.1.1.1", "1.2.3.4.5"])
def test_correlate_rejects_malformed_ip_without_treating_as_domain(bad_ip: str) -> None:
    events = FakeEventRepository({})
    with pytest.raises(ApplicationError) as error:
        DnsIntelligenceService(events=events).correlate(bad_ip, from_=FROM, to=TO)
    assert error.value.status_code == 400


# --- Authentication --------------------------------------------------------


class _StubRuntime:
    def check_ready(self) -> None:
        return None


def test_intelligence_endpoints_require_authentication() -> None:
    client = TestClient(create_app(_StubRuntime()))
    for path in (
        "/api/v1/intelligence/forward-dns?domain=example.com",
        "/api/v1/intelligence/reverse-dns?ip=8.8.8.8",
        "/api/v1/intelligence/dns-lookup?query=example.com&recordType=A",
        "/api/v1/intelligence/correlate?value=example.com",
    ):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "INVALID_TOKEN", path
