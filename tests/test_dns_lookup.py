from datetime import UTC, datetime
from typing import Any

import pytest

from backend.dns_lookup import DnsLookupError, forward_lookup, resolve_record, reverse_lookup
from backend.dns_service import DnsIntelligenceService

FROM = datetime(2026, 1, 1, tzinfo=UTC)
TO = datetime(2026, 1, 2, tzinfo=UTC)


class FakeEventRepository:
    """Stands in for storage.clickhouse.EventRepository: returns canned rows per filter."""

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
        remote_ip: str | None = None,
        dns_query: str | None = None,
        dns_answer_ip: str | None = None,
        l7_protocol: str | None = None,
    ) -> list[dict[str, Any]]:
        if remote_ip is not None:
            return self.rows_by_filter.get("remote_ip", [])
        if dns_answer_ip is not None:
            return self.rows_by_filter.get("dns_answer_ip", [])
        if domain is not None:
            return self.rows_by_filter.get("domain", [])
        if dns_query is not None:
            return self.rows_by_filter.get("dns_query", [])
        return []


# --- Live DNS tests --------------------------------------------------------
# These issue real DNS queries against public resolvers/domains, so they need
# outbound internet. Reverse (PTR) lookups in particular are unreliable inside
# some sandboxes/containers, so those skip (rather than fail) when unavailable.


def test_forward_lookup_returns_ip_addresses() -> None:
    addresses = forward_lookup("example.com")
    assert addresses
    assert all(isinstance(address, str) for address in addresses)


def test_resolve_record_mx_and_ns() -> None:
    assert resolve_record("google.com", "MX")
    assert resolve_record("google.com", "NS")


def test_reverse_lookup_known_ip() -> None:
    try:
        hostnames = reverse_lookup("8.8.8.8")
    except DnsLookupError as error:
        pytest.skip(f"reverse DNS unavailable in this environment: {error.code}")
    assert any("dns.google" in hostname for hostname in hostnames)


def test_forward_lookup_raises_for_missing_domain() -> None:
    # Some resolvers answer a nonexistent name with NXDOMAIN ("NOT_FOUND"); others
    # (e.g. ISP/router-level DNS helpers) return an empty NOERROR ("NO_ANSWER") instead.
    # Either way the domain is unusable, so we accept both codes here.
    with pytest.raises(DnsLookupError) as error:
        forward_lookup("this-domain-should-not-exist-abcxyz123456789.invalid")
    assert error.value.code in ("NOT_FOUND", "NO_ANSWER")


def test_reverse_lookup_rejects_invalid_ip() -> None:
    with pytest.raises(DnsLookupError) as error:
        reverse_lookup("not-an-ip")
    assert error.value.code == "INVALID_IP"


def test_resolve_record_rejects_unsupported_type() -> None:
    with pytest.raises(DnsLookupError) as error:
        resolve_record("example.com", "TXT")
    assert error.value.code == "UNSUPPORTED_RECORD_TYPE"


# --- Correlation logic tests ----------------------------------------------
# The live DNS layer is stubbed so these deterministically verify how the
# service merges live-DNS results with observed EDR event data.


def test_correlate_by_ip_combines_live_dns_and_observed_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.dns_service.reverse_lookup", lambda ip: ["dns.google"])
    events = FakeEventRepository(
        {
            "remote_ip": [{"remote_domain": "observed.example.com", "http_host": None, "tls_sni": None}],
            "dns_answer_ip": [{"dns_query": "resolved-from-answers.example.com"}],
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
            "domain": [{"remote_ip": "203.0.113.10"}],
            "dns_query": [{"remote_ip": None, "dns_answers_json": '["203.0.113.10", "203.0.113.11"]'}],
        }
    )
    result = DnsIntelligenceService(events=events).correlate("example.com", from_=FROM, to=TO)
    assert result.input_type == "DOMAIN"
    sources_by_value = {item.value: item.sources for item in result.related}
    assert sources_by_value["198.51.100.5"] == ["LIVE_DNS"]
    assert sources_by_value["203.0.113.10"] == ["OBSERVED_EVENTS"]
    assert sources_by_value["203.0.113.11"] == ["OBSERVED_EVENTS"]


def test_correlate_ignores_live_dns_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(ip: str) -> list[str]:
        raise DnsLookupError("TIMEOUT", "boom")

    monkeypatch.setattr("backend.dns_service.reverse_lookup", _boom)
    events = FakeEventRepository({"remote_ip": [{"remote_domain": "observed-only.example.com"}]})
    result = DnsIntelligenceService(events=events).correlate("203.0.113.99", from_=FROM, to=TO)
    assert result.input_type == "IP"
    assert [item.value for item in result.related] == ["observed-only.example.com"]
    assert result.related[0].sources == ["OBSERVED_EVENTS"]
