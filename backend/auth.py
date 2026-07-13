import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .contracts.enums import UserRole
from .errors import ApplicationError

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "edr-c-api"
JWT_AUDIENCE = "edr-c-dashboard"
JWT_EXPIRES_SECONDS = 900
REFRESH_TOKEN_BYTES = 32
PASSWORD_HASHER = PasswordHasher()
REQUIRED_CLAIMS = ["sub", "role", "sid", "jti", "iss", "aud", "iat", "nbf", "exp"]


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: int
    role: UserRole
    session_id: str


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def issue_access_token(
    *,
    user_id: int,
    role: UserRole,
    secret: str,
    now: datetime,
    session_id: str | None = None,
    ttl_seconds: int = JWT_EXPIRES_SECONDS,
    issuer: str = JWT_ISSUER,
    audience: str = JWT_AUDIENCE,
) -> str:
    issued_at = now.astimezone(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "sid": session_id or str(uuid4()),
        "jti": str(uuid4()),
        "iss": issuer,
        "aud": audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(
    token: str, *, secret: str, issuer: str = JWT_ISSUER, audience: str = JWT_AUDIENCE
) -> AuthenticatedUser:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            issuer=issuer,
            audience=audience,
            options={"require": REQUIRED_CLAIMS},
        )
        return AuthenticatedUser(
            user_id=int(payload["sub"]),
            role=UserRole(payload["role"]),
            session_id=str(payload["sid"]),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise ApplicationError(401, "INVALID_TOKEN", "The access token is invalid or expired.") from error


def require_write_role(user: AuthenticatedUser) -> None:
    if user.role not in {UserRole.ADMIN, UserRole.ANALYST}:
        raise ApplicationError(403, "FORBIDDEN", "The authenticated role cannot modify this resource.")
