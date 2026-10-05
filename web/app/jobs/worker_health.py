"""Private worker heartbeat; no network endpoint or secrets."""

import sys
import time
from pathlib import Path


def beat(name):
    Path(f"/tmp/absensa-{name}.heartbeat").touch()


def main():
    name = sys.argv[1]
    # Backups may legitimately take the configured maximum dump time.
    from app.core.config import settings

    limit = settings.backup_timeout_seconds + 300 if name == "backup" else 300
    try:
        healthy = (
            time.time() - Path(f"/tmp/absensa-{name}.heartbeat").stat().st_mtime < limit
        )
    except OSError:
        healthy = False
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
