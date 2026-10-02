"""Single dedicated backup worker; PostgreSQL locks also guard extra instances."""

import argparse
import logging
import os
import time

from app.db.session import engine
from app.services.backup_service import process_tick

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            state = process_tick(engine)
            if state not in {"idle", "busy"}:
                logger.info("Backup worker result: %s", state)
        except Exception:  # noqa: BLE001 - never log credentials from exception text
            # Raw subprocess/SDK/database exceptions can contain credentials.
            logger.error(
                "Backup worker failed; check configuration, storage and database availability"
            )
        if args.once:
            return
        time.sleep(10)


if __name__ == "__main__":
    main()
