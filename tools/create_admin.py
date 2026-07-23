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

PRODUCTION_MIN_PASSWORD_LENGTH = 16


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


def read_password(*, password_stdin: bool) -> str:
    if password_stdin:
        if sys.stdin.isatty():
            raise ValueError("--password-stdin requires redirected non-interactive input")
        return sys.stdin.readline().rstrip("\n")
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("password confirmation does not match")
    return password


def validate_password(password: str, *, environment: str) -> None:
    if not password:
        raise ValueError("password must not be empty")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must be at most {MAX_PASSWORD_LENGTH} characters")
    if environment.strip().lower() == "production" and len(password) < PRODUCTION_MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"production ADMIN password must be at least {PRODUCTION_MIN_PASSWORD_LENGTH} characters"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        login_id = normalize_login_id(args.login_id)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    settings = get_settings()
    try:
        password = read_password(password_stdin=args.password_stdin)
        validate_password(password, environment=settings.env)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
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
