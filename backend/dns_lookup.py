import ipaddress

import dns.exception
import dns.resolver
import dns.reversename

DEFAULT_TIMEOUT_SECONDS = 3.0
FORWARD_RECORD_TYPES = ("A", "AAAA", "MX", "NS")
SUPPORTED_RECORD_TYPES = (*FORWARD_RECORD_TYPES, "PTR")


class DnsLookupError(Exception):
    """A DNS lookup failed in an expected way (NXDOMAIN, timeout, no answer, bad input)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _resolver(timeout: float) -> dns.resolver.Resolver:
    resolver = dns.resolver.Resolver()
    resolver.timeout = timeout
    resolver.lifetime = timeout
    return resolver


def _format_answer(record_type: str, rdata: object) -> str:
    if record_type == "MX":
        return f"{rdata.preference} {rdata.exchange.to_text().rstrip('.')}"
    if record_type in ("NS", "PTR"):
        return rdata.to_text().rstrip(".")
    return rdata.to_text()


def resolve_record(domain: str, record_type: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
    """Query one forward DNS record type (A, AAAA, MX, NS) for a domain name."""
    record_type = record_type.upper()
    if record_type not in FORWARD_RECORD_TYPES:
        raise DnsLookupError("UNSUPPORTED_RECORD_TYPE", f"Unsupported record type: {record_type}")
    try:
        answer = _resolver(timeout).resolve(domain, record_type)
    except dns.resolver.NXDOMAIN as error:
        raise DnsLookupError("NOT_FOUND", f"Domain does not exist: {domain}") from error
    except dns.resolver.NoAnswer as error:
        raise DnsLookupError("NO_ANSWER", f"No {record_type} record for {domain}") from error
    except dns.resolver.NoNameservers as error:
        raise DnsLookupError("NO_NAMESERVERS", f"No nameservers could answer for {domain}") from error
    except dns.exception.Timeout as error:
        raise DnsLookupError("TIMEOUT", f"DNS lookup timed out for {domain}") from error
    return [_format_answer(record_type, rdata) for rdata in answer]


def forward_lookup(domain: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
    """Domain -> IP addresses. Tries A (IPv4) and AAAA (IPv6); a missing AAAA is not an error."""
    addresses: list[str] = []
    saw_not_found = False
    for record_type in ("A", "AAAA"):
        try:
            addresses.extend(resolve_record(domain, record_type, timeout=timeout))
        except DnsLookupError as error:
            if error.code == "NOT_FOUND":
                saw_not_found = True
            continue
    if not addresses:
        if saw_not_found:
            raise DnsLookupError("NOT_FOUND", f"Domain does not exist: {domain}")
        raise DnsLookupError("NO_ANSWER", f"No A or AAAA records for {domain}")
    return addresses


def reverse_lookup(ip: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
    """IP address -> hostnames (PTR record)."""
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError as error:
        raise DnsLookupError("INVALID_IP", f"Not a valid IP address: {ip}") from error
    reverse_name = dns.reversename.from_address(str(parsed))
    try:
        answer = _resolver(timeout).resolve(reverse_name, "PTR")
    except dns.resolver.NXDOMAIN as error:
        raise DnsLookupError("NOT_FOUND", f"No PTR record for {ip}") from error
    except dns.resolver.NoAnswer as error:
        raise DnsLookupError("NO_ANSWER", f"No PTR record for {ip}") from error
    except dns.resolver.NoNameservers as error:
        raise DnsLookupError("NO_NAMESERVERS", f"No nameservers could answer for {ip}") from error
    except dns.exception.Timeout as error:
        raise DnsLookupError("TIMEOUT", f"DNS lookup timed out for {ip}") from error
    return [_format_answer("PTR", rdata) for rdata in answer]


def lookup(query: str, record_type: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
    """General nslookup-style entry point: A, AAAA, MX, NS, or PTR for the given query."""
    record_type = record_type.upper()
    if record_type == "PTR":
        return reverse_lookup(query, timeout=timeout)
    if record_type not in FORWARD_RECORD_TYPES:
        raise DnsLookupError("UNSUPPORTED_RECORD_TYPE", f"Unsupported record type: {record_type}")
    return resolve_record(query, record_type, timeout=timeout)
