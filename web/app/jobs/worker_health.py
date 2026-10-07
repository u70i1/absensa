"""Private worker heartbeat; no network endpoint or secrets."""

import os
import sys
import tempfile
import time
from pathlib import Path


def heartbeat_path(name):
    return (
        Path(os.environ.get("ABSENSA_HEARTBEAT_DIR", tempfile.gettempdir()))
        / f"absensa-{name}.heartbeat"
    )


def beat(name):
    heartbeat_path(name).touch()


def main():
    name = sys.argv[1]
    # Backups may legitimately take the configured maximum dump time.
    from app.core.config import settings

    limit = settings.backup_timeout_seconds + 300 if name == "backup" else 300
    try:
        healthy = time.time() - heartbeat_path(name).stat().st_mtime < limit
    except OSError:
        healthy = False
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
