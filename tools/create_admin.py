import argparse
import getpass
import sys
from datetime import UTC, datetime

import psycopg
from psycopg.errors import UniqueViolation

from backend.auth import hash_password
from backend.contracts.auth import MAX_PASSWORD_LENGTH, normalize_login_id
from backend.settings import get_settings
from backend.storage.postgres import UserRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an ACTIVE Dashboard ADMIN or reset its local credentials.")
    parser.add_argument("--login-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password-stdin", action="store_true", help="Read one password line from stdin.")
    parser.add_argument(
        "--reset-existing",
        action="store_true",
        help="Reset the password, name, role, and status when the login ID already exists.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = sys.stdin.readline().rstrip("\n") if args.password_stdin else getpass.getpass("Password: ")
    if not password:
        print("password must not be empty", file=sys.stderr)
        return 2
    if len(password) > MAX_PASSWORD_LENGTH:
        print(f"password must be at most {MAX_PASSWORD_LENGTH} characters", file=sys.stderr)
        return 2
    try:
        login_id = normalize_login_id(args.login_id)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    settings = get_settings()
    if args.reset_existing and settings.env != "local":
        print("--reset-existing is allowed only when EDR_ENV=local", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(settings.postgres_dsn.get_secret_value()) as connection:
            repository = UserRepository(connection)
            password_hash = hash_password(password)
            now = datetime.now(UTC)
            user_id = None
            action = "created"
            if args.reset_existing:
                user_id = repository.reset_admin_credentials(
                    login_id=login_id,
                    name=args.name,
                    password_hash=password_hash,
                    now=now,
                )
                if user_id is not None:
                    action = "reset"
            if user_id is None:
                user_id = repository.create_admin(
                    login_id=login_id,
                    name=args.name,
                    password_hash=password_hash,
                    now=now,
                )
    except UniqueViolation:
        print(f"login ID already exists: {login_id}", file=sys.stderr)
        return 2
    print(f"{action} ADMIN user_id={user_id} login_id={login_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
