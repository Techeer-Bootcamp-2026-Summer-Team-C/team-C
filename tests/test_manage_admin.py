from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from tools.manage_admin import (
    ADMIN_LIFECYCLE_LOCK_ID,
    _safe_snapshot,
    _validated_mutation_context,
    disable_admin,
    main,
    soft_delete_admin,
)

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def _user(
    user_id: int,
    login_id: str,
    *,
    role: str = "ADMIN",
    status: str = "ACTIVE",
    is_delete: bool = False,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "login_id": login_id,
        "password_hash": "$argon2id$sensitive-hash",
        "name": f"User {user_id}",
        "role": role,
        "status": status,
        "is_delete": is_delete,
        "last_login_at": NOW,
    }


class _Result:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _FakeConnection:
    def __init__(self, *users: dict[str, Any]) -> None:
        self.users = {int(user["user_id"]): dict(user) for user in users}
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.audit_params: list[tuple[Any, ...]] = []

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @contextmanager
    def transaction(self) -> Any:
        yield

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> _Result:
        normalized = " ".join(query.split())
        self.statements.append((normalized, params))

        if normalized.startswith("SELECT pg_advisory_xact_lock"):
            assert params == (ADMIN_LIFECYCLE_LOCK_ID,)
            return _Result({"pg_advisory_xact_lock": None})

        if normalized.startswith("SELECT user_id, login_id") and "FROM users WHERE user_id = %s" in normalized:
            user = self.users.get(int(params[0]))
            return _Result(dict(user) if user is not None else None)

        if normalized.startswith("SELECT count(*) AS active_admin_count"):
            count = sum(
                user["role"] == "ADMIN" and user["status"] == "ACTIVE" and not user["is_delete"]
                for user in self.users.values()
            )
            return _Result({"active_admin_count": count})

        if normalized.startswith("UPDATE users SET status = 'DISABLED'"):
            now, user_id = params
            user = self.users[int(user_id)]
            if user["role"] != "ADMIN" or user["status"] != "ACTIVE" or user["is_delete"]:
                return _Result()
            user["status"] = "DISABLED"
            user["updated_at"] = now
            return _Result(dict(user))

        if normalized.startswith("UPDATE users SET is_delete = TRUE"):
            now, user_id = params
            user = self.users[int(user_id)]
            if user["role"] != "ADMIN" or user["status"] != "DISABLED" or user["is_delete"]:
                return _Result()
            user["is_delete"] = True
            user["password_hash"] = "!"
            user["updated_at"] = now
            return _Result(dict(user))

        if normalized.startswith("INSERT INTO audit_logs"):
            self.audit_params.append(params)
            return _Result()

        raise AssertionError(f"unexpected SQL: {normalized}")


class _Secret:
    def __init__(self, value: str) -> None:
        self.value = value

    def get_secret_value(self) -> str:
        return self.value


def test_safe_snapshot_never_exposes_credentials() -> None:
    snapshot = _safe_snapshot(_user(7, "mentor-review"))

    assert snapshot == {
        "userId": 7,
        "loginId": "mentor-review",
        "name": "User 7",
        "role": "ADMIN",
        "status": "ACTIVE",
        "isDelete": False,
        "lastLoginAt": "2026-07-23T12:00:00+00:00",
    }
    assert "password" not in str(snapshot).lower()


def test_mutation_context_requires_an_exact_nonempty_environment() -> None:
    assert _validated_mutation_context(
        actual_environment=" Production ",
        confirmed_environment="production",
        operator=" release-owner ",
        reason=" presentation complete ",
    ) == ("release-owner", "presentation complete")

    with pytest.raises(RuntimeError, match="does not match"):
        _validated_mutation_context(
            actual_environment="production",
            confirmed_environment="staging",
            operator="release-owner",
            reason="presentation complete",
        )
    with pytest.raises(RuntimeError, match="must not be empty"):
        _validated_mutation_context(
            actual_environment=" ",
            confirmed_environment=" ",
            operator="release-owner",
            reason="presentation complete",
        )


def test_disable_admin_serializes_and_records_a_safe_audit() -> None:
    connection = _FakeConnection(_user(1, "mentor-review"), _user(2, "backup-admin"))

    action, snapshot = disable_admin(
        connection,
        user_id=1,
        expected_login_id=" MENTOR-REVIEW ",
        operator="release-owner",
        reason="presentation complete",
        allow_no_active_admin=False,
        now=NOW,
    )

    assert action == "disabled"
    assert snapshot["status"] == "DISABLED"
    assert connection.statements[0][0].startswith("SELECT pg_advisory_xact_lock")
    assert connection.users[1]["status"] == "DISABLED"
    assert len(connection.audit_params) == 1
    assert connection.audit_params[0][0] == "manage-admin:release-owner"
    assert connection.audit_params[0][1] == "DASHBOARD_ADMIN_DISABLED"
    assert "sensitive-hash" not in str(connection.audit_params)


def test_disable_admin_protects_the_final_active_admin() -> None:
    connection = _FakeConnection(_user(1, "mentor-review"))

    with pytest.raises(RuntimeError, match="final ACTIVE ADMIN"):
        disable_admin(
            connection,
            user_id=1,
            expected_login_id="mentor-review",
            operator="release-owner",
            reason="presentation complete",
            allow_no_active_admin=False,
            now=NOW,
        )

    assert connection.users[1]["status"] == "ACTIVE"
    assert connection.audit_params == []


def test_disable_admin_allows_explicit_final_admin_removal() -> None:
    connection = _FakeConnection(_user(1, "mentor-review"))

    action, _ = disable_admin(
        connection,
        user_id=1,
        expected_login_id="mentor-review",
        operator="release-owner",
        reason="presentation complete",
        allow_no_active_admin=True,
        now=NOW,
    )

    assert action == "disabled"
    assert connection.users[1]["status"] == "DISABLED"


def test_admin_mutations_require_the_exact_login_and_admin_role() -> None:
    admin_connection = _FakeConnection(_user(1, "mentor-review"), _user(2, "backup-admin"))
    viewer_connection = _FakeConnection(_user(3, "mentor-viewer", role="VIEWER"))

    with pytest.raises(RuntimeError, match="login ID does not match"):
        disable_admin(
            admin_connection,
            user_id=1,
            expected_login_id="different-admin",
            operator="release-owner",
            reason="presentation complete",
            allow_no_active_admin=False,
            now=NOW,
        )
    with pytest.raises(RuntimeError, match="not an ADMIN"):
        disable_admin(
            viewer_connection,
            user_id=3,
            expected_login_id="mentor-viewer",
            operator="release-owner",
            reason="presentation complete",
            allow_no_active_admin=True,
            now=NOW,
        )


def test_soft_delete_requires_disable_and_tombstones_the_password_hash() -> None:
    active_connection = _FakeConnection(_user(1, "mentor-review"))
    disabled_connection = _FakeConnection(_user(1, "mentor-review", status="DISABLED"))

    with pytest.raises(RuntimeError, match="must be DISABLED"):
        soft_delete_admin(
            active_connection,
            user_id=1,
            expected_login_id="mentor-review",
            operator="release-owner",
            reason="presentation complete",
            now=NOW,
        )

    action, snapshot = soft_delete_admin(
        disabled_connection,
        user_id=1,
        expected_login_id="mentor-review",
        operator="release-owner",
        reason="presentation complete",
        now=NOW,
    )

    assert action == "soft-deleted"
    assert snapshot["isDelete"] is True
    assert disabled_connection.users[1]["password_hash"] == "!"
    assert disabled_connection.audit_params[0][1] == "DASHBOARD_ADMIN_SOFT_DELETED"


def test_main_rejects_environment_mismatch_before_opening_the_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = SimpleNamespace(env="production", postgres_dsn=_Secret("postgresql://user:secret@postgres/edr"))
    monkeypatch.setattr("tools.manage_admin.get_settings", lambda: settings)

    def unexpected_connect(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("database connection must not be opened")

    monkeypatch.setattr("tools.manage_admin.psycopg.connect", unexpected_connect)

    result = main(
        [
            "disable",
            "--user-id",
            "1",
            "--confirm-login-id",
            "mentor-review",
            "--confirm-environment",
            "staging",
            "--operator",
            "release-owner",
            "--reason",
            "presentation complete",
        ]
    )

    assert result == 2
    assert "does not match EDR_ENV" in capsys.readouterr().err


def test_inspect_rejects_non_admin_and_never_prints_the_dsn(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dsn = "postgresql://user:do-not-print@postgres/edr"
    settings = SimpleNamespace(env="production", postgres_dsn=_Secret(dsn))
    connection = _FakeConnection(_user(3, "mentor-viewer", role="VIEWER"))
    monkeypatch.setattr("tools.manage_admin.get_settings", lambda: settings)
    monkeypatch.setattr("tools.manage_admin.psycopg.connect", lambda *_args, **_kwargs: connection)

    result = main(["inspect", "--user-id", "3"])
    output = capsys.readouterr()

    assert result == 2
    assert "not an ADMIN" in output.err
    assert dsn not in output.err
    assert dsn not in output.out


def test_inspect_prints_only_the_safe_admin_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dsn = "postgresql://user:do-not-print@postgres/edr"
    settings = SimpleNamespace(env="production", postgres_dsn=_Secret(dsn))
    connection = _FakeConnection(_user(1, "mentor-review"))
    monkeypatch.setattr("tools.manage_admin.get_settings", lambda: settings)
    monkeypatch.setattr("tools.manage_admin.psycopg.connect", lambda *_args, **_kwargs: connection)

    result = main(["inspect", "--user-id", "1"])
    output = capsys.readouterr()

    assert result == 0
    assert '"action": "inspected"' in output.out
    assert '"loginId": "mentor-review"' in output.out
    assert "sensitive-hash" not in output.out
    assert dsn not in output.out
    assert output.err == ""
