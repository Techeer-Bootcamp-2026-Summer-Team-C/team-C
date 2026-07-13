from typing import Literal

from pydantic import field_validator

from .common import ContractModel, NonNegativeInt, PositiveId
from .enums import UserRole, UserStatus


class LoginRequest(ContractModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserDto(ContractModel):
    user_id: PositiveId
    email: str
    name: str
    role: UserRole
    status: UserStatus


class LoginData(ContractModel):
    access_token: str
    token_type: Literal["Bearer"]
    expires_in: NonNegativeInt
    user: UserDto
