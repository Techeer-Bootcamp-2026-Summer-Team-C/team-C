from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.contracts.auth import normalize_login_id
from backend.settings import get_settings

LAST_ADMIN_REMOVAL_CONFIRMATION = "ALLOW_NO_ACTIVE_ADMIN"
ADMIN_LIFECYCLE_LOCK_ID = 1_164_209_217


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect, disable, or soft-delete one explicitly identified ADMIN.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Read one ADMIN without changing it.")
    inspect_parser.add_argument("--user-id", type=int, required=True)

    for action in ("disable", "soft-delete"):
        action_parser = subparsers.add_parser(action)
        action_parser.add_argument("--user-id", type=int, required=True)
        action_parser.add_argument("--confirm-login-id", required=True)
        action_parser.add_argument("--confirm-environment", required=True)
        action_parser.add_argument("--operator", required=True)
        action_parser.add_argument("--reason", required=True)
        if action == "disable":
            action_parser.add_argument(
                "--confirm-last-admin-removal",
                help=f"Required only when this is the final ACTIVE ADMIN: {LAST_ADMIN_REMOVAL_CONFIRMATION}",
            )
    return parser


def _safe_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": int(row["user_id"]),
        "loginId": str(row["login_id"]),
        "name": str(row["name"]),
        "role": str(row["role"]),
        "status": str(row["status"]),
        "isDelete": bool(row["is_delete"]),
        "lastLoginAt": row["last_login_at"].isoformat() if row["last_login_at"] is not None else None,
    }


def _fetch_user(
    connection: psycopg.Connection,
    user_id: int,
    *,
    for_update: bool,
) -> dict[str, Any] | None:
    suffix = " FOR UPDATE" if for_update else ""
    row = connection.execute(
        f"""
        SELECT user_id, login_id, name, role, status, is_delete, last_login_at
        FROM users
        WHERE user_id = %s{suffix}
        """,
        (user_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _require_admin(
    row: dict[str, Any] | None,
    *,
    user_id: int,
) -> dict[str, Any]:
    if row is None:
        raise RuntimeError(f"user_id={user_id} does not exist")
    if str(row["role"]) != "ADMIN":
        raise RuntimeError("selected user is not an ADMIN")
    return row


def _validated_admin(
    row: dict[str, Any] | None,
    *,
    user_id: int,
    expected_login_id: str,
) -> dict[str, Any]:
    row = _require_admin(row, user_id=user_id)
    normalized_login_id = normalize_login_id(expected_login_id)
    if str(row["login_id"]) != normalized_login_id:
        raise RuntimeError("confirmed login ID does not match the selected user")
    return row


def _lock_admin_lifecycle(connection: psycopg.Connection) -> None:
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (ADMIN_LIFECYCLE_LOCK_ID,))


def _audit(
    connection: psycopg.Connection,
    *,
    user_id: int,
    operator: str,
    action: str,
    before: dict[str, Any],
    after: dict[str, Any],
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_logs (
            actor_type, actor_identifier, action, resource_type, resource_id,
            before_json, after_json, request_id, created_at
        ) VALUES ('SYSTEM', %s, %s, 'USER', %s, %s, %s, %s, %s)
        """,
        (
            f"manage-admin:{operator}",
            action,
            str(user_id),
            Jsonb(before),
            Jsonb(after),
            f"cli_{uuid4()}",
            now,
        ),
    )


def disable_admin(
    connection: psycopg.Connection,
    *,
    user_id: int,
    expected_login_id: str,
    operator: str,
    reason: str,
    allow_no_active_admin: bool,
    now: datetime,
) -> tuple[str, dict[str, Any]]:
    with connection.transaction():
        _lock_admin_lifecycle(connection)
        row = _validated_admin(
            _fetch_user(connection, user_id, for_update=True),
            user_id=user_id,
            expected_login_id=expected_login_id,
        )
        if bool(row["is_delete"]):
            raise RuntimeError("selected ADMIN is already soft-deleted")
        if str(row["status"]) == "DISABLED":
            return "already-disabled", _safe_snapshot(row)
        count_row = connection.execute(
            """
            SELECT count(*) AS active_admin_count FROM users
            WHERE role = 'ADMIN' AND status = 'ACTIVE' AND is_delete = FALSE
            """
        ).fetchone()
        if count_row is None:
            raise RuntimeError("ACTIVE ADMIN count query failed")
        active_admin_count = int(count_row["active_admin_count"])
        if active_admin_count <= 1 and not allow_no_active_admin:
            raise RuntimeError("refusing to disable the final ACTIVE ADMIN without --confirm-last-admin-removal")
        before = _safe_snapshot(row)
        updated = connection.execute(
            """
            UPDATE users
            SET status = 'DISABLED', updated_at = %s
            WHERE user_id = %s AND role = 'ADMIN' AND status = 'ACTIVE' AND is_delete = FALSE
            RETURNING user_id, login_id, name, role, status, is_delete, last_login_at
            """,
            (now, user_id),
        ).fetchone()
        if updated is None:
            raise RuntimeError("ADMIN disable failed")
        after = _safe_snapshot(dict(updated))
        _audit(
            connection,
            user_id=user_id,
            operator=operator,
            action="DASHBOARD_ADMIN_DISABLED",
            before=before,
            after={**after, "reason": reason},
            now=now,
        )
        return "disabled", after


def soft_delete_admin(
    connection: psycopg.Connection,
    *,
    user_id: int,
    expected_login_id: str,
    operator: str,
    reason: str,
    now: datetime,
) -> tuple[str, dict[str, Any]]:
    with connection.transaction():
        _lock_admin_lifecycle(connection)
        row = _validated_admin(
            _fetch_user(connection, user_id, for_update=True),
            user_id=user_id,
            expected_login_id=expected_login_id,
        )
        if bool(row["is_delete"]):
            return "already-soft-deleted", _safe_snapshot(row)
        if str(row["status"]) != "DISABLED":
            raise RuntimeError("ADMIN must be DISABLED before soft-delete")
        before = _safe_snapshot(row)
        updated = connection.execute(
            """
            UPDATE users
            SET is_delete = TRUE, password_hash = '!', updated_at = %s
            WHERE user_id = %s AND role = 'ADMIN' AND status = 'DISABLED' AND is_delete = FALSE
            RETURNING user_id, login_id, name, role, status, is_delete, last_login_at
            """,
            (now, user_id),
        ).fetchone()
        if updated is None:
            raise RuntimeError("ADMIN soft-delete failed")
        after = _safe_snapshot(dict(updated))
        _audit(
            connection,
            user_id=user_id,
            operator=operator,
            action="DASHBOARD_ADMIN_SOFT_DELETED",
            before=before,
            after={**after, "reason": reason},
            now=now,
        )
        return "soft-deleted", after


def _validated_mutation_context(
    *,
    actual_environment: str,
    confirmed_environment: str,
    operator: str,
    reason: str,
) -> tuple[str, str]:
    normalized_environment = actual_environment.strip().lower()
    if not normalized_environment:
        raise RuntimeError("EDR_ENV must not be empty")
    if confirmed_environment.strip().lower() != normalized_environment:
        raise RuntimeError("--confirm-environment does not match EDR_ENV")
    normalized_operator = operator.strip()
    normalized_reason = reason.strip()
    if not normalized_operator or len(normalized_operator) > 64:
        raise ValueError("operator must be 1-64 characters")
    if not normalized_reason or len(normalized_reason) > 255:
        raise ValueError("reason must be 1-255 characters")
    return normalized_operator, normalized_reason


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.user_id < 1:
        print("user-id must be positive", file=sys.stderr)
        return 2
    settings = get_settings()
    try:
        mutation_context: tuple[str, str] | None = None
        if args.action != "inspect":
            mutation_context = _validated_mutation_context(
                actual_environment=settings.env,
                confirmed_environment=args.confirm_environment,
                operator=args.operator,
                reason=args.reason,
            )
        with psycopg.connect(
            settings.postgres_dsn.get_secret_value(),
            row_factory=dict_row,
        ) as connection:
            if args.action == "inspect":
                row = _fetch_user(connection, args.user_id, for_update=False)
                row = _require_admin(row, user_id=args.user_id)
                result = {"action": "inspected", "user": _safe_snapshot(row)}
            else:
                if mutation_context is None:
                    raise RuntimeError("ADMIN mutation context was not validated")
                operator, reason = mutation_context
                if args.action == "disable":
                    confirmation = args.confirm_last_admin_removal
                    if confirmation not in {None, LAST_ADMIN_REMOVAL_CONFIRMATION}:
                        raise RuntimeError("--confirm-last-admin-removal value is invalid")
                    action, user = disable_admin(
                        connection,
                        user_id=args.user_id,
                        expected_login_id=args.confirm_login_id,
                        operator=operator,
                        reason=reason,
                        allow_no_active_admin=confirmation == LAST_ADMIN_REMOVAL_CONFIRMATION,
                        now=datetime.now(UTC),
                    )
                else:
                    action, user = soft_delete_admin(
                        connection,
                        user_id=args.user_id,
                        expected_login_id=args.confirm_login_id,
                        operator=operator,
                        reason=reason,
                        now=datetime.now(UTC),
                    )
                result = {"action": action, "user": user}
    except (RuntimeError, ValueError, psycopg.Error) as error:
        print(f"ADMIN management failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
