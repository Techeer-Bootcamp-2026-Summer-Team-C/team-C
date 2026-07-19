import re
from typing import Annotated, Literal

from pydantic import Field, field_validator

from .common import ContractModel, NonNegativeInt, PositiveId
from .enums import UserLocale, UserRole, UserStatus

LOGIN_ID_PATTERN = r"^[a-z0-9][a-z0-9._@+-]{2,63}$"
MAX_PASSWORD_LENGTH = 1024
LoginId = Annotated[
    str,
    Field(
        min_length=3,
        max_length=64,
        pattern=LOGIN_ID_PATTERN,
        description="로그인에 사용하는 사용자 ID입니다. 영문 소문자로 정규화됩니다.",
        examples=["frontend-admin@example.com"],
    ),
]
Password = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PASSWORD_LENGTH, description="사용자 비밀번호입니다."),
]


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
    locale: UserLocale = Field(description="대시보드 표시 언어입니다.", examples=["KO"])


class LoginData(ContractModel):
    access_token: str = Field(description="후속 API 요청의 Authorization 헤더에 사용할 JWT입니다.")
    token_type: Literal["Bearer"] = Field(description="토큰 인증 유형입니다.")
    expires_in: NonNegativeInt = Field(description="액세스 토큰 만료까지 남은 초입니다.")
    user: UserDto = Field(description="로그인한 사용자 정보입니다.")
