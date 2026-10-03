"""Create or reset an admin; --first-only only bootstraps the first account."""

import argparse
import sys
from getpass import getpass

from app.db.session import SessionLocal
from app.schemas.admin import AdminLoginRequest
from app.services import admin_auth_service
from pydantic import ValidationError


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Buat administrator atau ganti sandinya; --first-only hanya membuat akun pertama."
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Baca sandi dari stdin (digunakan installer)",
    )
    parser.add_argument(
        "--first-only",
        action="store_true",
        help="Buat admin hanya jika belum ada akun admin",
    )
    parser.add_argument("username", help="Nama pengguna administrator")
    args = parser.parse_args()
    if args.password_stdin:
        if sys.stdin.isatty():
            raise SystemExit("--password-stdin harus menerima masukan melalui pipa.")
        password = sys.stdin.readline(1026).rstrip("\n")
    else:
        password = getpass("Sandi: ")
        if password != getpass("Ulangi sandi: "):
            raise SystemExit("Sandi tidak sama.")
    if not 8 <= len(password) <= 1024:
        raise SystemExit("Sandi harus berisi 8–1024 karakter.")
    try:
        credentials = AdminLoginRequest(username=args.username, password=password)
    except ValidationError as exc:
        raise SystemExit("Nama pengguna dan sandi tidak boleh kosong.") from exc

    with SessionLocal() as db:
        create = (
            admin_auth_service.bootstrap_first_admin
            if args.first_only
            else admin_auth_service.set_admin_credentials
        )
        admin = create(db, credentials.username, credentials.password)
    print(
        "Akun admin yang ada dipertahankan."
        if admin is None
        else "Akun administrator siap."
    )


if __name__ == "__main__":
    main()
