from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .contracts.enums import UserRole
from .errors import ApplicationError

JWT_ALGORITHM = "HS256"
JWT_EXPIRES_SECONDS = 3600
PASSWORD_HASHER = PasswordHasher()


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: int
    role: UserRole


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def issue_access_token(*, user_id: int, role: UserRole, secret: str, now: datetime) -> str:
    issued_at = now.astimezone(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=JWT_EXPIRES_SECONDS),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> AuthenticatedUser:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
        return AuthenticatedUser(user_id=int(payload["sub"]), role=UserRole(payload["role"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise ApplicationError(401, "INVALID_TOKEN", "The access token is invalid or expired.") from error


def require_write_role(user: AuthenticatedUser) -> None:
    if user.role not in {UserRole.ADMIN, UserRole.ANALYST}:
        raise ApplicationError(403, "FORBIDDEN", "The authenticated role cannot modify this resource.")
