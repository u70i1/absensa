"""Create local deployment settings without overwriting existing credentials.

Uses only Python's standard library; also runnable inside a Python container.
"""

import argparse
import os
import secrets
from pathlib import Path

TIMEZONES = ("Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura")


def write_config(destination: Path, port: int, timezone: str = "Asia/Jakarta") -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("Choose a web port between 1024 and 65535.")
    if timezone not in TIMEZONES:
        raise ValueError("Choose an Indonesian time zone.")
    content = (
        "# Private deployment configuration. Keep with your protected backups.\n"
        f"ABSENSA_PORT={port}\n"
        "ABSENSA_BIND=0.0.0.0\n"
        "ABSENSA_VERSION=local\n"
        f"TIMEZONE={timezone}\n"
        "COOKIE_SECURE=false\n"
        f"POSTGRES_PASSWORD={secrets.token_hex(32)}\n"
        f"WHATSAPP_BRIDGE_TOKEN={secrets.token_hex(32)}\n"
    )
    # O_EXCL prevents accidental password rotation against an existing database.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
        target.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--timezone", choices=TIMEZONES, default="Asia/Jakarta")
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("production.env")
    )
    args = parser.parse_args()
    try:
        write_config(args.output, args.port, args.timezone)
    except (FileExistsError, ValueError) as exc:
        raise SystemExit(
            "Configuration already exists; it was not changed."
            if isinstance(exc, FileExistsError) else str(exc)
        ) from exc
    print(f"Created {args.output}. Keep it private; do not commit it.")


if __name__ == "__main__":
    main()
