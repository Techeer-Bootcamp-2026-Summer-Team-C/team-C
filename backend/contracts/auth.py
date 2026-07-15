import re
from typing import Annotated, Literal

from pydantic import Field, field_validator

from .common import ContractModel, NonNegativeInt, PositiveId
from .enums import UserLocale, UserRole, UserStatus

LOGIN_ID_PATTERN = r"^[a-z0-9][a-z0-9._@+-]{2,63}$"
MAX_PASSWORD_LENGTH = 1024
LoginId = Annotated[str, Field(min_length=3, max_length=64, pattern=LOGIN_ID_PATTERN)]
Password = Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)]


def normalize_login_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("login_id must be a string")
    normalized = value.strip().lower()
    if re.fullmatch(LOGIN_ID_PATTERN, normalized) is None:
        raise ValueError("login_id must be 3-64 characters using letters, numbers, '.', '_', '@', '+', or '-'")
    return normalized


class LoginRequest(ContractModel):
    login_id: LoginId
    password: Password

    @field_validator("login_id", mode="before")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        return normalize_login_id(value)


class UserDto(ContractModel):
    user_id: PositiveId
    login_id: LoginId
    name: str
    role: UserRole
    status: UserStatus
    locale: UserLocale


class UserLocaleUpdateRequest(ContractModel):
    locale: UserLocale


class LoginData(ContractModel):
    access_token: str
    token_type: Literal["Bearer"]
    expires_in: NonNegativeInt
    user: UserDto
