import io

import pytest

from tools.create_admin import read_password, validate_password


def test_interactive_password_requires_matching_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(("correct horse battery staple", "different value"))
    monkeypatch.setattr("tools.create_admin.getpass.getpass", lambda _: next(responses))

    with pytest.raises(ValueError, match="confirmation does not match"):
        read_password(password_stdin=False)


def test_interactive_password_returns_the_confirmed_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(("correct horse battery staple", "correct horse battery staple"))
    monkeypatch.setattr("tools.create_admin.getpass.getpass", lambda _: next(responses))

    assert read_password(password_stdin=False) == "correct horse battery staple"


def test_password_stdin_keeps_the_non_interactive_single_line_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tools.create_admin.sys.stdin", io.StringIO("stdin-password\nignored\n"))

    assert read_password(password_stdin=True) == "stdin-password"


def test_password_stdin_rejects_an_interactive_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = io.StringIO("visible-password\n")
    monkeypatch.setattr(terminal, "isatty", lambda: True)
    monkeypatch.setattr("tools.create_admin.sys.stdin", terminal)

    with pytest.raises(ValueError, match="redirected non-interactive"):
        read_password(password_stdin=True)


def test_production_admin_password_requires_at_least_sixteen_characters() -> None:
    with pytest.raises(ValueError, match="at least 16"):
        validate_password("short-password", environment="production")
    with pytest.raises(ValueError, match="at least 16"):
        validate_password("short-password", environment="Production")

    validate_password("sixteen-chars-ok", environment="production")
    validate_password("short-password", environment="local")
