"""Single dedicated backup worker; PostgreSQL locks also guard extra instances."""

import argparse
import logging
import os
import time

from app.jobs.worker_health import beat
from app.db.session import engine
from app.services.backup_service import process_tick

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--manual", action="store_true", help="Create a backup now; requires --once"
    )
    args = parser.parse_args()
    if args.manual and not args.once:
        parser.error("--manual requires --once")
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            state = process_tick(engine, manual=args.manual)
            beat("backup")
            if state not in {"idle", "busy"}:
                logger.info("Backup worker result: %s", state)
        except Exception:  # noqa: BLE001 - never log credentials from exception text
            # Raw subprocess/SDK/database exceptions can contain credentials.
            logger.error(
                "Backup worker failed; check configuration, storage and database availability"
            )
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            if state in {"failed", "busy"} or (args.manual and state != "success"):
                raise SystemExit(1)
            return
        time.sleep(10)


if __name__ == "__main__":
    main()
