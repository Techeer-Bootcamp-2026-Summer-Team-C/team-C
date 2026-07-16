import ipaddress
import json
from datetime import datetime

from .contracts.enums import DnsRecordType
from .contracts.intelligence import CorrelationDto, DnsLookupDto, ForwardDnsDto, RelatedValueDto, ReverseDnsDto
from .dns_lookup import DnsLookupError, forward_lookup, reverse_lookup
from .dns_lookup import lookup as raw_lookup
from .errors import ApplicationError
from .storage.clickhouse import EventRepository


def _to_application_error(error: DnsLookupError) -> ApplicationError:
    if error.code in ("NOT_FOUND", "NO_ANSWER"):
        return ApplicationError(404, "NOT_FOUND", error.message)
    if error.code in ("INVALID_IP", "UNSUPPORTED_RECORD_TYPE"):
        return ApplicationError(400, "VALIDATION_ERROR", error.message)
    return ApplicationError(503, "SERVICE_UNAVAILABLE", error.message, True)


def _looks_like_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


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
            addresses = forward_lookup(domain)
        except DnsLookupError as error:
            raise _to_application_error(error) from error
        return ForwardDnsDto(domain=domain, ip_addresses=addresses)

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

    def correlate(self, value: str, *, from_: datetime, to: datetime) -> CorrelationDto:
        is_ip = _looks_like_ip(value)
        related: dict[str, set[str]] = {}

        def add(candidate: str | None, source: str) -> None:
            if candidate:
                related.setdefault(candidate, set()).add(source)

        try:
            if is_ip:
                for hostname in reverse_lookup(value):
                    add(hostname, "LIVE_DNS")
            else:
                for address in forward_lookup(value):
                    add(address, "LIVE_DNS")
        except DnsLookupError:
            pass  # a correlation lookup should still return what our own events know

        if is_ip:
            for row in self.events.search(from_=from_, to=to, remote_ip=value):
                add(row.get("remote_domain"), "OBSERVED_EVENTS")
                add(row.get("http_host"), "OBSERVED_EVENTS")
                add(row.get("tls_sni"), "OBSERVED_EVENTS")
            for row in self.events.search(from_=from_, to=to, dns_answer_ip=value):
                add(row.get("dns_query"), "OBSERVED_EVENTS")
        else:
            for row in self.events.search(from_=from_, to=to, domain=value):
                add(row.get("remote_ip"), "OBSERVED_EVENTS")
            for row in self.events.search(from_=from_, to=to, dns_query=value):
                add(row.get("remote_ip"), "OBSERVED_EVENTS")
                for answer in _parse_dns_answers(row.get("dns_answers_json")):
                    add(answer, "OBSERVED_EVENTS")

        items = [
            RelatedValueDto(
                value=candidate,
                value_type="IP" if _looks_like_ip(candidate) else "DOMAIN",
                sources=sorted(sources),
            )
            for candidate, sources in related.items()
        ]
        items.sort(key=lambda item: (-len(item.sources), item.value))
        return CorrelationDto(
            input_value=value,
            input_type="IP" if is_ip else "DOMAIN",
            from_=from_,
            to=to,
            related=items,
        )
