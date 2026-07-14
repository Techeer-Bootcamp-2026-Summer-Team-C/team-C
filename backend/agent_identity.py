import re
from datetime import UTC, datetime
from urllib.parse import unquote

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from fastapi import Header

from .errors import InvalidAgentCertificateError
from .storage.models import AgentCertificateIdentity

AGENT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
AGENT_URI_PREFIX = "urn:edr:agent:"


def _certificate_time(value: str) -> datetime:
    for pattern in ("%b %d %H:%M:%S %Y GMT", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise InvalidAgentCertificateError()


def _identity_from_verified_certificate(value: str) -> AgentCertificateIdentity:
    try:
        certificate = x509.load_pem_x509_certificate(unquote(value).encode("ascii"))
        san_values = list(certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value)
    except (UnicodeEncodeError, ValueError, x509.ExtensionNotFound) as error:
        raise InvalidAgentCertificateError() from error

    if len(san_values) != 1 or not isinstance(san_values[0], x509.UniformResourceIdentifier):
        raise InvalidAgentCertificateError()
    uri = san_values[0].value
    if not uri.startswith(AGENT_URI_PREFIX):
        raise InvalidAgentCertificateError()
    agent_id = uri.removeprefix(AGENT_URI_PREFIX)
    if AGENT_ID_PATTERN.fullmatch(agent_id) is None:
        raise InvalidAgentCertificateError()

    return AgentCertificateIdentity(
        subject=certificate.subject.rfc4514_string(),
        san_agent_id=agent_id,
        fingerprint_sha256=certificate.fingerprint(hashes.SHA256()).hex(),
        issued_at=certificate.not_valid_before_utc,
        expires_at=certificate.not_valid_after_utc,
    )


def trusted_agent_identity(
    verified: str | None = Header(None, alias="X-EDR-mTLS-Verify", include_in_schema=False),
    certificate: str | None = Header(None, alias="X-EDR-Client-Certificate", include_in_schema=False),
    subject: str | None = Header(None, alias="X-EDR-Certificate-Subject", include_in_schema=False),
    san_agent_id: str | None = Header(None, alias="X-EDR-Certificate-SAN-Agent-ID", include_in_schema=False),
    fingerprint: str | None = Header(None, alias="X-EDR-Certificate-Fingerprint-SHA256", include_in_schema=False),
    not_before: str | None = Header(None, alias="X-EDR-Certificate-Not-Before", include_in_schema=False),
    not_after: str | None = Header(None, alias="X-EDR-Certificate-Not-After", include_in_schema=False),
) -> AgentCertificateIdentity:
    if verified != "SUCCESS":
        raise InvalidAgentCertificateError()
    if certificate:
        return _identity_from_verified_certificate(certificate)
    if not all((subject, san_agent_id, fingerprint, not_before, not_after)):
        raise InvalidAgentCertificateError()
    normalized_fingerprint = fingerprint.replace(":", "").lower()
    invalid_character = any(character not in "0123456789abcdef" for character in normalized_fingerprint)
    if len(normalized_fingerprint) != 64 or invalid_character:
        raise InvalidAgentCertificateError()
    return AgentCertificateIdentity(
        subject=subject,
        san_agent_id=san_agent_id,
        fingerprint_sha256=normalized_fingerprint,
        issued_at=_certificate_time(not_before),
        expires_at=_certificate_time(not_after),
    )
