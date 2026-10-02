"""Offline recovery helper. Decrypts a tar archive; never restores a database."""

import argparse
import os
from pathlib import Path

from app.services.backup_crypto_service import decrypt_archive, encryption_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        decrypt_archive(args.source, args.destination, encryption_key())
    except Exception:  # noqa: BLE001 - sanitized CLI error
        raise SystemExit(
            "Decryption failed: check the encryption key and archive integrity."
        ) from None
    print(
        "Authenticated archive decrypted. Protect and remove plaintext after recovery."
    )


if __name__ == "__main__":
    main()
