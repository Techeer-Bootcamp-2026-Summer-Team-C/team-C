import os

import pytest

from backend.dns_lookup import DnsLookupError, forward_lookup, resolve_record, reverse_lookup

# These tests issue REAL DNS queries against public resolvers/domains, so they need
# outbound internet and are excluded from the normal (deterministic) unit run. Enable
# them explicitly with EDR_RUN_DNS_LIVE=1. Reverse (PTR) lookups in particular are
# unreliable inside sandboxes/containers.
RUN_LIVE = os.getenv("EDR_RUN_DNS_LIVE") == "1"
pytestmark = pytest.mark.skipif(not RUN_LIVE, reason="live DNS disabled; set EDR_RUN_DNS_LIVE=1 to enable")


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
    # return an empty NOERROR ("NO_ANSWER"). Either way the domain is unusable.
    with pytest.raises(DnsLookupError) as error:
        forward_lookup("this-domain-should-not-exist-abcxyz123456789.invalid")
    assert error.value.code in ("NOT_FOUND", "NO_ANSWER")
