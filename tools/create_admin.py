import argparse
import getpass
import sys
from datetime import UTC, datetime

import psycopg
from psycopg.errors import UniqueViolation

from backend.auth import hash_password
from backend.settings import get_settings
from backend.storage.postgres import UserRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create the initial ACTIVE Dashboard ADMIN.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password-stdin", action="store_true", help="Read one password line from stdin.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = sys.stdin.readline().rstrip("\n") if args.password_stdin else getpass.getpass("Password: ")
    if not password:
        print("password must not be empty", file=sys.stderr)
        return 2
    settings = get_settings()
    try:
        with psycopg.connect(settings.postgres_dsn.get_secret_value()) as connection:
            user_id = UserRepository(connection).create_admin(
                email=args.email,
                name=args.name,
                password_hash=hash_password(password),
                now=datetime.now(UTC),
            )
    except UniqueViolation:
        print(f"email already exists: {args.email.strip().lower()}", file=sys.stderr)
        return 2
    print(f"created ADMIN user_id={user_id} email={args.email.strip().lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
