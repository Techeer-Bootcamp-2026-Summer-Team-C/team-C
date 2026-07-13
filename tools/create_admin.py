import argparse
import getpass
import sys
from datetime import UTC, datetime

import psycopg

from backend.auth import hash_password
from backend.settings import get_settings
from backend.storage.postgres import UserRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or reset the ACTIVE Dashboard ADMIN account.")
    parser.add_argument("--login-id", required=True, help="Login email/id for the account.")
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--reset-existing",
        action="store_true",
        help="If the account already exists, reset its password/name instead of failing.",
    )
    parser.add_argument("--password-stdin", action="store_true", help="Read one password line from stdin.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = sys.stdin.readline().rstrip("\n") if args.password_stdin else getpass.getpass("Password: ")
    if not password:
        print("password must not be empty", file=sys.stderr)
        return 2
    login_id = args.login_id.strip().lower()
    settings = get_settings()
    with psycopg.connect(settings.postgres_dsn.get_secret_value()) as connection:
        repository = UserRepository(connection)
        existing = repository.by_email(login_id)
        if existing is not None:
            if not args.reset_existing:
                print(f"account already exists: {login_id} (pass --reset-existing to overwrite)", file=sys.stderr)
                return 2
            user_id = repository.reset_admin(
                user_id=existing["user_id"],
                name=args.name,
                password_hash=hash_password(password),
                now=datetime.now(UTC),
            )
            print(f"reset ADMIN user_id={user_id} email={login_id}")
            return 0
        user_id = repository.create_admin(
            email=login_id,
            name=args.name,
            password_hash=hash_password(password),
            now=datetime.now(UTC),
        )
    print(f"created ADMIN user_id={user_id} email={login_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
