from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend.agent_identity import _identity_from_verified_certificate
from backend.errors import InvalidAgentCertificateError


def _certificate(*, san: x509.GeneralName) -> x509.Certificate:
    now = datetime.now(UTC).replace(microsecond=0)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "compose-demo-agent")])
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([san]), critical=False)
        .sign(key, hashes.SHA256())
    )


def test_derives_identity_from_nginx_escaped_verified_certificate() -> None:
    certificate = _certificate(san=x509.UniformResourceIdentifier("urn:edr:agent:compose-demo-agent"))
    escaped_pem = quote(certificate.public_bytes(serialization.Encoding.PEM).decode("ascii"), safe="")

    identity = _identity_from_verified_certificate(escaped_pem)

    assert identity.subject == "CN=compose-demo-agent"
    assert identity.san_agent_id == "compose-demo-agent"
    assert identity.fingerprint_sha256 == certificate.fingerprint(hashes.SHA256()).hex()
    assert identity.issued_at == certificate.not_valid_before_utc
    assert identity.expires_at == certificate.not_valid_after_utc


def test_rejects_certificate_without_agent_uri_san() -> None:
    certificate = _certificate(san=x509.DNSName("localhost"))
    pem = certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")

    with pytest.raises(InvalidAgentCertificateError):
        _identity_from_verified_certificate(pem)
