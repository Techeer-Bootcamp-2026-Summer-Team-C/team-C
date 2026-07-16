import ipaddress

import dns.exception
import dns.resolver
import dns.reversename

DEFAULT_TIMEOUT_SECONDS = 3.0
FORWARD_RECORD_TYPES = ("A", "AAAA", "MX", "NS")
SUPPORTED_RECORD_TYPES = (*FORWARD_RECORD_TYPES, "PTR")
MAX_DOMAIN_LENGTH = 253
MAX_LABEL_LENGTH = 63
# Errors that mean "the resolver could not determine an answer" (vs. an authoritative
# "does not exist"). These must be preserved so the API can map them to 503, not 404.
INFRASTRUCTURE_CODES = ("TIMEOUT", "NO_NAMESERVERS")


class DnsLookupError(Exception):
    """A DNS lookup failed in an expected way (NXDOMAIN, timeout, no answer, bad input)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_domain(domain: str) -> str:
    """Validate and canonicalize a domain name: trim, lowercase, drop the trailing dot.

    Rejects empty/oversized names, empty or oversized labels, and names that are not
    valid IDNA. Raises DnsLookupError("INVALID_DOMAIN", ...) which maps to HTTP 400.
    """
    candidate = domain.strip().rstrip(".").lower()
    if not candidate:
        raise DnsLookupError("INVALID_DOMAIN", "Domain must not be empty")
    if len(candidate) > MAX_DOMAIN_LENGTH:
        raise DnsLookupError("INVALID_DOMAIN", f"Domain exceeds {MAX_DOMAIN_LENGTH} characters: {domain}")
    labels = candidate.split(".")
    for label in labels:
        if not label:
            raise DnsLookupError("INVALID_DOMAIN", f"Domain has an empty label: {domain}")
        if len(label) > MAX_LABEL_LENGTH:
            raise DnsLookupError("INVALID_DOMAIN", f"Domain label exceeds {MAX_LABEL_LENGTH} characters: {domain}")
    try:
        candidate.encode("idna")
    except (UnicodeError, ValueError) as error:
        raise DnsLookupError("INVALID_DOMAIN", f"Domain is not a valid name: {domain}") from error
    return candidate


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
    domain = normalize_domain(domain)
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
    """Domain -> IP addresses. Tries A (IPv4) and AAAA (IPv6); a missing AAAA is not an error.

    If both queries fail, the error is preserved by severity rather than flattened: an
    infrastructure failure (TIMEOUT / NO_NAMESERVERS) is raised so the API returns 503,
    NXDOMAIN is raised as NOT_FOUND, and only a true empty answer becomes NO_ANSWER.
    """
    domain = normalize_domain(domain)
    addresses: list[str] = []
    errors: list[DnsLookupError] = []
    for record_type in ("A", "AAAA"):
        try:
            addresses.extend(resolve_record(domain, record_type, timeout=timeout))
        except DnsLookupError as error:
            errors.append(error)
    if addresses:
        return addresses
    for error in errors:
        if error.code in INFRASTRUCTURE_CODES:
            raise error
    for error in errors:
        if error.code == "NOT_FOUND":
            raise error
    raise DnsLookupError("NO_ANSWER", f"No A or AAAA records for {domain}")


def reverse_lookup(ip: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
    """IP address -> hostnames (PTR record).

    Private/internal IPs (RFC 1918, loopback, link-local) are intentionally NOT blocked:
    in an EDR investigation an internal IP is a legitimate lookup target, and the PTR query
    resolves names only (it does not open a connection to the host). Risk to accept: a caller
    can make the backend resolver issue PTR queries for arbitrary IPs, which could probe
    internal reverse-DNS naming. If that becomes a concern, gate internal ranges behind a
    setting or require an elevated role rather than removing the capability outright.
    """
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
