import pytest
from pydantic import ValidationError

from backend.contracts.auth import LoginRequest, UserDto, UserLocaleUpdateRequest, normalize_login_id
from backend.contracts.enums import UserLocale, UserRole, UserStatus


def test_login_id_is_user_defined_case_insensitive_and_not_email_only() -> None:
    request = LoginRequest.model_validate({"loginId": " Security-Admin ", "password": "secret"})
    user = UserDto(
        user_id=1,
        login_id=request.login_id,
        name="Security Admin",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        locale=UserLocale.EN,
    )

    assert request.login_id == "security-admin"
    assert user.model_dump(mode="json", by_alias=True)["loginId"] == "security-admin"
    assert normalize_login_id("legacy@example.com") == "legacy@example.com"


def test_user_locale_contract_is_required_and_accepts_only_en_or_ko() -> None:
    assert UserLocaleUpdateRequest.model_validate({"locale": "KO"}).locale is UserLocale.KO
    with pytest.raises(ValidationError):
        UserLocaleUpdateRequest.model_validate({"locale": "JA"})
    with pytest.raises(ValidationError):
        UserDto.model_validate(
            {
                "userId": 1,
                "loginId": "security-admin",
                "name": "Security Admin",
                "role": "ADMIN",
                "status": "ACTIVE",
            }
        )


@pytest.mark.parametrize("login_id", ["ab", "has space", "_starts-with-symbol", "한글아이디"])
def test_invalid_login_ids_are_rejected(login_id: str) -> None:
    with pytest.raises((ValidationError, ValueError)):
        LoginRequest.model_validate({"loginId": login_id, "password": "secret"})


@pytest.mark.parametrize("password", ["", "x" * 1025])
def test_empty_and_oversized_passwords_are_rejected(password: str) -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({"loginId": "security-admin", "password": password})
