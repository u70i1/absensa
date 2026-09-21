"""Create an administrator or replace an existing administrator's password."""

import argparse
from getpass import getpass

from app.db.session import SessionLocal
from app.schemas.admin import AdminLoginRequest
from app.services import admin_auth_service
from pydantic import ValidationError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Administrator username")
    args = parser.parse_args()
    password = getpass("Password: ")
    confirmation = getpass("Repeat password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters.")
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
