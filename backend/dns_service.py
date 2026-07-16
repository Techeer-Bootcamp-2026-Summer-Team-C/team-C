"""DNS intelligence service.

Scope of this feature (read-only):
  - Live DNS lookups (forward / reverse / record types) via the backend resolver.
  - Correlation of an IP or domain against ALREADY-OBSERVED EDR event data.

Explicitly out of scope here (follow-up work):
  - Persisting IP<->Domain relationships as first-class entities/edges.
  - eTLD+1 / Public Suffix based subdomain parent-child modelling.
  - The Intelligence dashboard graph/visualisation.

Principles:
  - "Live DNS" is resolved by the backend server (not the endpoint's local resolver).
    If per-endpoint resolver/cache correlation is needed later, the Agent must collect it.
  - PTR results never replace the IP; they are surfaced as candidate domains with a source.
"""

import ipaddress
import json
from datetime import datetime

from .contracts.enums import DnsRecordType
from .contracts.intelligence import CorrelationDto, DnsLookupDto, ForwardDnsDto, RelatedValueDto, ReverseDnsDto
from .dns_lookup import DnsLookupError, forward_lookup, normalize_domain, reverse_lookup
from .dns_lookup import lookup as raw_lookup
from .errors import ApplicationError
from .storage.clickhouse import EventRepository


def _to_application_error(error: DnsLookupError) -> ApplicationError:
    if error.code in ("NOT_FOUND", "NO_ANSWER"):
        return ApplicationError(404, "NOT_FOUND", error.message)
    if error.code in ("INVALID_IP", "INVALID_DOMAIN", "UNSUPPORTED_RECORD_TYPE"):
        return ApplicationError(400, "VALIDATION_ERROR", error.message)
    return ApplicationError(503, "SERVICE_UNAVAILABLE", error.message, True)


def _canonical(value: str) -> tuple[str, str]:
    """Canonicalize a related value for dedupe (lenient, never raises).

    IPs collapse to their canonical form (so different IPv6 notations dedupe); domains
    are lowercased with the trailing dot stripped. Returns (canonical_value, value_type).
    """
    stripped = value.strip()
    try:
        return ipaddress.ip_address(stripped).compressed, "IP"
    except ValueError:
        return stripped.rstrip(".").lower(), "DOMAIN"


def _classify_target(value: str) -> tuple[str, bool]:
    """Classify a correlate target as a valid IP or a valid domain (strict, raises on bad input).

    Returns (canonical_value, is_ip). A value that looks like an IP attempt (contains ':' or
    is only digits and dots) but does not parse as an IP is rejected as INVALID_IP rather than
    being silently treated as a domain name.
    """
    stripped = value.strip()
    if not stripped:
        raise DnsLookupError("INVALID_DOMAIN", "Value must not be empty")
    looks_like_ip_attempt = ":" in stripped or (
        "." in stripped and all(part.isdigit() for part in stripped.split("."))
    )
    if looks_like_ip_attempt:
        try:
            return ipaddress.ip_address(stripped).compressed, True
        except ValueError as error:
            raise DnsLookupError("INVALID_IP", f"Not a valid IP address: {value}") from error
    return normalize_domain(stripped), False


def _parse_dns_answers(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


class DnsIntelligenceService:
    def __init__(self, *, events: EventRepository) -> None:
        self.events = events

    def forward(self, domain: str) -> ForwardDnsDto:
        try:
            normalized = normalize_domain(domain)
            addresses = forward_lookup(normalized)
        except DnsLookupError as error:
            raise _to_application_error(error) from error
        return ForwardDnsDto(domain=normalized, ip_addresses=addresses)

    def reverse(self, ip: str) -> ReverseDnsDto:
        try:
            hostnames = reverse_lookup(ip)
        except DnsLookupError as error:
            raise _to_application_error(error) from error
        return ReverseDnsDto(ip=ip, hostnames=hostnames)

    def lookup(self, query: str, record_type: DnsRecordType) -> DnsLookupDto:
        try:
            answers = raw_lookup(query, record_type.value)
        except DnsLookupError as error:
            raise _to_application_error(error) from error
        return DnsLookupDto(query=query, record_type=record_type, answers=answers)

    def correlate(
        self,
        value: str,
        *,
        from_: datetime,
        to: datetime,
        endpoint_ids: list[int] | None = None,
    ) -> CorrelationDto:
        try:
            target, is_ip = _classify_target(value)
        except DnsLookupError as error:
            raise _to_application_error(error) from error
        # `related` is keyed by the CANONICAL value, so a value found through several search
        # paths, from both live DNS and our events, or written in a different-but-equivalent
        # form (trailing dot, mixed case, alternate IPv6 notation) is deduped into one row
        # with its sources merged.
        related: dict[str, tuple[str, set[str]]] = {}

        def add(candidate: str | None, source: str) -> None:
            if not candidate:
                return
            canonical, value_type = _canonical(str(candidate))
            if not canonical:
                return
            related.setdefault(canonical, (value_type, set()))[1].add(source)

        try:
            if is_ip:
                # PTR results are candidate domains only: they may be absent, stale, or point at
                # a CDN/hosting hostname rather than the site actually contacted. We surface them
                # alongside the IP with a LIVE_DNS source; we never replace the IP with the PTR name.
                for hostname in reverse_lookup(target):
                    add(hostname, "LIVE_DNS")
            else:
                for address in forward_lookup(target):
                    add(address, "LIVE_DNS")
        except DnsLookupError:
            pass  # a correlation lookup should still return what our own events know

        if is_ip:
            for row in self.events.search(from_=from_, to=to, endpoint_ids=endpoint_ids, remote_ip=target):
                add(row.get("remote_domain"), "OBSERVED_EVENTS")
                add(row.get("http_host"), "OBSERVED_EVENTS")
                add(row.get("tls_sni"), "OBSERVED_EVENTS")
            for row in self.events.search(from_=from_, to=to, endpoint_ids=endpoint_ids, dns_answer_ip=target):
                add(row.get("dns_query"), "OBSERVED_EVENTS")
        else:
            # related_domain matches the exact name or a subdomain across remote_domain,
            # http_host, tls_sni, and dns_query; from each matched event we collect both the
            # contacted IP and any resolved answer IPs.
            for row in self.events.search(from_=from_, to=to, endpoint_ids=endpoint_ids, related_domain=target):
                add(row.get("remote_ip"), "OBSERVED_EVENTS")
                for answer in _parse_dns_answers(row.get("dns_answers_json")):
                    add(answer, "OBSERVED_EVENTS")

        items = [
            RelatedValueDto(value=canonical, value_type=value_type, sources=sorted(sources))
            for canonical, (value_type, sources) in related.items()
        ]
        items.sort(key=lambda item: (-len(item.sources), item.value))
        return CorrelationDto(
            input_value=target,
            input_type="IP" if is_ip else "DOMAIN",
            from_=from_,
            to=to,
            related=items,
        )
