"""Authenticate an encrypted backup without writing plaintext or restoring data."""

import argparse
from pathlib import Path

from app.services.backup_crypto_service import encryption_key, verify_archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    try:
        verify_archive(args.source, encryption_key())
    except Exception:  # noqa: BLE001 - do not expose secrets in CLI errors
        raise SystemExit(
            "Verification failed: check the encryption key and archive integrity."
        ) from None
    print(
        "Archive authentication passed. Rehearse database and photo recovery separately."
    )


if __name__ == "__main__":
    main()
