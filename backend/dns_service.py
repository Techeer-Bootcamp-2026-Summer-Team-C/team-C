"""DNS intelligence service.

Scope of this feature (read-only):
  - Live DNS lookups (forward / reverse / record types) via the backend resolver.
  - Correlation of an IP or domain against ALREADY-OBSERVED EDR event data.
  - Query-time IP/domain/subdomain relationships for the Intelligence workspace.

Explicitly out of scope here (follow-up work):
  - Persisting derived IP<->Domain relationships as first-class entities/edges.
  - eTLD+1 / Public Suffix based subdomain parent-child modelling.

Principles:
  - "Live DNS" is resolved by the backend server (not the endpoint's local resolver).
    If per-endpoint resolver/cache correlation is needed later, the Agent must collect it.
  - PTR results never replace the IP; they are surfaced as candidate domains with a source.
"""

import ipaddress
import json
import logging
from datetime import datetime

from .contracts.enums import DnsRecordType
from .contracts.intelligence import (
    CorrelationDto,
    CorrelationRelationshipDto,
    DnsLookupDto,
    ForwardDnsDto,
    RelatedValueDto,
    ReverseDnsDto,
)
from .dns_lookup import DnsLookupError, forward_lookup, normalize_domain, reverse_lookup
from .dns_lookup import lookup as raw_lookup
from .errors import ApplicationError
from .storage.clickhouse import EventRepository

LOGGER = logging.getLogger(__name__)
MAX_CORRELATION_EVENTS = 10_000
MAX_CORRELATION_VALUES = 20_000
CORRELATION_EVENT_COLUMNS = [
    "remote_domain",
    "http_host",
    "tls_sni",
    "remote_ip",
    "dns_query",
    "dns_answers_json",
]


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
        relationships: dict[tuple[str, str, str], tuple[str, str, set[str]]] = {}

        def add(candidate: str | None, source: str) -> tuple[str, str] | None:
            if not candidate:
                return None
            canonical, value_type = _canonical(str(candidate))
            if not canonical:
                return None
            if canonical != target:
                if canonical not in related and len(related) >= MAX_CORRELATION_VALUES:
                    raise _correlation_too_large()
                related.setdefault(canonical, (value_type, set()))[1].add(source)
            return canonical, value_type

        def relate(source_value: str, target_value: str, relation: str, evidence_source: str) -> None:
            source = add(source_value, evidence_source)
            destination = add(target_value, evidence_source)
            if source is None or destination is None:
                return
            source_canonical, source_type = source
            target_canonical, target_type = destination
            key = (relation, source_canonical, target_canonical)
            if key not in relationships and len(relationships) >= MAX_CORRELATION_VALUES:
                raise _correlation_too_large()
            relationships.setdefault(key, (source_type, target_type, set()))[2].add(evidence_source)

        def observed_domain(row: dict[str, object], field: str) -> str | None:
            raw = row.get(field)
            if not raw:
                return None
            canonical, value_type = _canonical(str(raw))
            return canonical if value_type == "DOMAIN" and canonical else None

        def in_domain_scope(candidate: str, parent: str) -> bool:
            return candidate == parent or candidate.endswith(f".{parent}")

        try:
            if is_ip:
                # PTR results are candidate domains only: they may be absent, stale, or point at
                # a CDN/hosting hostname rather than the site actually contacted. We surface them
                # alongside the IP with a LIVE_DNS source; we never replace the IP with the PTR name.
                for hostname in reverse_lookup(target):
                    relate(target, hostname, "PTR_CANDIDATE", "LIVE_DNS")
            else:
                for address in forward_lookup(target):
                    relate(target, address, "RESOLVES_TO", "LIVE_DNS")
        except DnsLookupError as error:
            LOGGER.warning("live DNS correlation lookup failed code=%s", error.code)

        remaining = MAX_CORRELATION_EVENTS
        if is_ip:
            remote_rows, remaining = self._event_rows(
                remaining,
                from_=from_,
                to=to,
                endpoint_ids=endpoint_ids,
                remote_ip=target,
            )
            for row in remote_rows:
                for field in ("remote_domain", "http_host", "tls_sni"):
                    domain = observed_domain(row, field)
                    if domain:
                        relate(domain, target, "RESOLVES_TO", "OBSERVED_EVENTS")
            answer_rows, remaining = self._event_rows(
                remaining,
                from_=from_,
                to=to,
                endpoint_ids=endpoint_ids,
                dns_answer_ip=target,
            )
            for row in answer_rows:
                domain = observed_domain(row, "dns_query")
                if domain:
                    relate(domain, target, "RESOLVES_TO", "OBSERVED_EVENTS")
        else:
            # related_domain matches the exact name or a subdomain across remote_domain,
            # http_host, tls_sni, and dns_query; from each matched event we collect both the
            # contacted IP and any resolved answer IPs.
            domain_rows, remaining = self._event_rows(
                remaining,
                from_=from_,
                to=to,
                endpoint_ids=endpoint_ids,
                related_domain=target,
            )
            for row in domain_rows:
                matching_domains: set[str] = set()
                for field in ("remote_domain", "http_host", "tls_sni", "dns_query"):
                    domain = observed_domain(row, field)
                    if domain and in_domain_scope(domain, target):
                        matching_domains.add(domain)
                        add(domain, "OBSERVED_EVENTS")
                        if domain != target:
                            relate(domain, target, "SUBDOMAIN_OF", "OBSERVED_EVENTS")

                remote_ip = row.get("remote_ip")
                if remote_ip:
                    for field in ("remote_domain", "http_host", "tls_sni"):
                        domain = observed_domain(row, field)
                        if domain in matching_domains:
                            relate(domain, str(remote_ip), "RESOLVES_TO", "OBSERVED_EVENTS")

                dns_query = observed_domain(row, "dns_query")
                for answer in _parse_dns_answers(row.get("dns_answers_json")):
                    if dns_query in matching_domains:
                        relate(dns_query, answer, "RESOLVES_TO", "OBSERVED_EVENTS")

        items = [
            RelatedValueDto(value=canonical, value_type=value_type, sources=sorted(sources))
            for canonical, (value_type, sources) in related.items()
        ]
        items.sort(key=lambda item: (-len(item.sources), item.value))
        relationship_items = [
            CorrelationRelationshipDto(
                source_value=source_value,
                source_type=source_type,
                target_value=target_value,
                target_type=target_type,
                relation=relation,
                sources=sorted(sources),
            )
            for (relation, source_value, target_value), (source_type, target_type, sources) in relationships.items()
        ]
        relationship_items.sort(key=lambda item: (item.relation, item.source_value, item.target_value))
        return CorrelationDto(
            input_value=target,
            input_type="IP" if is_ip else "DOMAIN",
            from_=from_,
            to=to,
            related=items,
            relationships=relationship_items,
        )

    def _event_rows(self, remaining: int, **filters: object) -> tuple[list[dict[str, object]], int]:
        if remaining <= 0:
            raise _correlation_too_large()
        rows = self.events.search(
            **filters,
            columns=CORRELATION_EVENT_COLUMNS,
            limit=remaining + 1,
        )
        if len(rows) > remaining:
            raise _correlation_too_large()
        return rows, remaining - len(rows)


def _correlation_too_large() -> ApplicationError:
    return ApplicationError(
        400,
        "VALIDATION_ERROR",
        (
            f"Correlation range contains more than {MAX_CORRELATION_EVENTS} events; "
            "narrow the time range or Endpoint filter."
        ),
    )
