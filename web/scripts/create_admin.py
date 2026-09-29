"""Create an administrator or replace an existing administrator's password."""

import argparse
import sys
from getpass import getpass

from app.db.session import SessionLocal
from app.schemas.admin import AdminLoginRequest
from app.services import admin_auth_service
from pydantic import ValidationError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one password line from a pipe (used by the setup wizard)",
    )
    parser.add_argument("username", help="Administrator username")
    args = parser.parse_args()
    if args.password_stdin:
        if sys.stdin.isatty():
            raise SystemExit("--password-stdin requires a pipe.")
        password = sys.stdin.readline(1026).rstrip("\n")
    else:
        password = getpass("Password: ")
        if password != getpass("Repeat password: "):
            raise SystemExit("Passwords do not match.")
    if not 8 <= len(password) <= 1024:
        raise SystemExit("Password must contain 8 to 1024 characters.")
    try:
        credentials = AdminLoginRequest(username=args.username, password=password)
    except ValidationError as exc:
        raise SystemExit("Username and password must not be empty.") from exc

    with SessionLocal() as db:
        admin = admin_auth_service.set_admin_credentials(
            db, credentials.username, credentials.password
        )
    print(f'Admin "{admin.username}" is ready.')


if __name__ == "__main__":
    main()
