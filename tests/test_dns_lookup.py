from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.dns_lookup import DnsLookupError, resolve_record, reverse_lookup
from backend.dns_service import DnsIntelligenceService
from backend.main import create_app
from backend.storage.clickhouse import EventRepository

FROM = datetime(2026, 1, 1, tzinfo=UTC)
TO = datetime(2026, 1, 2, tzinfo=UTC)


class FakeEventRepository:
    """Stands in for EventRepository: returns canned rows keyed by the active filter."""

    def __init__(self, rows_by_filter: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_filter = rows_by_filter

    def search(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
        event_type: str | None = None,
        process_name: str | None = None,
        file_path: str | None = None,
        domain: str | None = None,
        related_domain: str | None = None,
        remote_ip: str | None = None,
        dns_query: str | None = None,
        dns_answer_ip: str | None = None,
        l7_protocol: str | None = None,
    ) -> list[dict[str, Any]]:
        if remote_ip is not None:
            return self.rows_by_filter.get("remote_ip", [])
        if dns_answer_ip is not None:
            return self.rows_by_filter.get("dns_answer_ip", [])
        if related_domain is not None:
            return self.rows_by_filter.get("related_domain", [])
        return []


class RecordingClient:
    """Captures the SQL/parameters EventRepository builds, without a real ClickHouse."""

    def __init__(self) -> None:
        self.last_query: str | None = None
        self.last_parameters: dict[str, Any] | None = None

    def query(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
        self.last_query = query
        self.last_parameters = parameters
        return SimpleNamespace(result_rows=[])


# --- Error-path DNS util tests (no network needed) -------------------------


def test_reverse_lookup_rejects_invalid_ip() -> None:
    with pytest.raises(DnsLookupError) as error:
        reverse_lookup("not-an-ip")
    assert error.value.code == "INVALID_IP"


def test_resolve_record_rejects_unsupported_type() -> None:
    with pytest.raises(DnsLookupError) as error:
        resolve_record("example.com", "TXT")
    assert error.value.code == "UNSUPPORTED_RECORD_TYPE"


# --- SQL construction: domain boundary + JSON array membership -------------
# These prove EventRepository.search builds boundary-safe SQL (no real DB needed).


def test_related_domain_uses_exact_and_subdomain_boundary_not_substring() -> None:
    client = RecordingClient()
    EventRepository(client).search(from_=FROM, to=TO, related_domain="yahoo.com")
    query = client.last_query or ""
    # exact-name match and subdomain (".yahoo.com") boundary via endsWith, across columns
    assert "= lowerUTF8({related_domain:String})" in query
    assert "endsWith(lowerUTF8(ifNull(remote_domain, '')), lowerUTF8(concat('.', {related_domain:String})))" in query
    assert "dns_query" in query and "tls_sni" in query and "http_host" in query
    # must NOT fall back to substring matching for related_domain
    assert "positionCaseInsensitiveUTF8(ifNull(remote_domain, ''), {related_domain:String})" not in query
    assert client.last_parameters == {"from": FROM, "to": TO, "related_domain": "yahoo.com"}


def test_dns_answer_ip_uses_json_array_membership_not_quoted_substring() -> None:
    client = RecordingClient()
    EventRepository(client).search(from_=FROM, to=TO, dns_answer_ip="1.2.3.4")
    query = client.last_query or ""
    assert "has(JSONExtract(ifNull(dns_answers_json, '[]'), 'Array(String)'), {dns_answer_ip:String})" in query
    assert "concat('\"'" not in query  # the old quoted-substring approach is gone
    assert client.last_parameters == {"from": FROM, "to": TO, "dns_answer_ip": "1.2.3.4"}


def test_events_ui_domain_filter_keeps_substring_matching() -> None:
    # The Events UI free-text `domain` filter is intentionally left as substring matching;
    # only correlation uses the precise `related_domain` boundary.
    client = RecordingClient()
    EventRepository(client).search(from_=FROM, to=TO, domain="yahoo")
    query = client.last_query or ""
    assert "positionCaseInsensitiveUTF8(ifNull(remote_domain, ''), {domain:String})" in query


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


def test_correlate_by_domain_combines_forward_dns_and_observed_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.dns_service.forward_lookup", lambda domain: ["198.51.100.5"])
    events = FakeEventRepository(
        {
            "related_domain": [
                {"endpoint_id": 1, "remote_ip": "203.0.113.10", "dns_answers_json": '["203.0.113.10", "203.0.113.11"]'},
            ]
        }
    )
    result = DnsIntelligenceService(events=events).correlate("example.com", from_=FROM, to=TO)
    assert result.input_type == "DOMAIN"
    sources_by_value = {item.value: item.sources for item in result.related}
    assert sources_by_value["198.51.100.5"] == ["LIVE_DNS"]
    assert sources_by_value["203.0.113.10"] == ["OBSERVED_EVENTS"]
    assert sources_by_value["203.0.113.11"] == ["OBSERVED_EVENTS"]


def test_correlate_keeps_observed_events_when_live_dns_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(ip: str) -> list[str]:
        raise DnsLookupError("TIMEOUT", "resolver unavailable")

    monkeypatch.setattr("backend.dns_service.reverse_lookup", _boom)
    events = FakeEventRepository({"remote_ip": [{"endpoint_id": 1, "remote_domain": "observed-only.example.com"}]})
    result = DnsIntelligenceService(events=events).correlate("203.0.113.99", from_=FROM, to=TO)
    assert result.input_type == "IP"
    assert [item.value for item in result.related] == ["observed-only.example.com"]
    assert result.related[0].sources == ["OBSERVED_EVENTS"]


def test_correlate_dedupes_value_seen_from_multiple_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    # "shared.example.com" is returned by BOTH live PTR and an observed event: it must appear
    # exactly once, with both sources merged.
    monkeypatch.setattr("backend.dns_service.reverse_lookup", lambda ip: ["shared.example.com"])
    events = FakeEventRepository({"remote_ip": [{"endpoint_id": 1, "remote_domain": "shared.example.com"}]})
    result = DnsIntelligenceService(events=events).correlate("8.8.8.8", from_=FROM, to=TO)
    matching = [item for item in result.related if item.value == "shared.example.com"]
    assert len(matching) == 1
    assert matching[0].sources == ["LIVE_DNS", "OBSERVED_EVENTS"]


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
