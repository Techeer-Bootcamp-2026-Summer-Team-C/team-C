from datetime import UTC, datetime

from fastapi import Header

from .errors import InvalidAgentCertificateError
from .storage.models import AgentCertificateIdentity


def _certificate_time(value: str) -> datetime:
    for pattern in ("%b %d %H:%M:%S %Y GMT", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise InvalidAgentCertificateError()


def trusted_agent_identity(
    verified: str | None = Header(None, alias="X-EDR-mTLS-Verify", include_in_schema=False),
    subject: str | None = Header(None, alias="X-EDR-Certificate-Subject", include_in_schema=False),
    san_agent_id: str | None = Header(None, alias="X-EDR-Certificate-SAN-Agent-ID", include_in_schema=False),
    fingerprint: str | None = Header(None, alias="X-EDR-Certificate-Fingerprint-SHA256", include_in_schema=False),
    not_before: str | None = Header(None, alias="X-EDR-Certificate-Not-Before", include_in_schema=False),
    not_after: str | None = Header(None, alias="X-EDR-Certificate-Not-After", include_in_schema=False),
) -> AgentCertificateIdentity:
    if verified != "SUCCESS" or not all((subject, san_agent_id, fingerprint, not_before, not_after)):
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
