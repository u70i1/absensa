"""Private local storage for encrypted archives and physical backup copies."""

import os
import re
from pathlib import Path

from app.core.config import settings
from app.services.exceptions import AppException


class LocalBackupStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.backups_dir).resolve()

    def prepare(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def path(self, backup_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", backup_id):
            raise AppException("Cadangan tidak ditemukan.", 404)
        path = self.root / f"{backup_id}.absbackup"
        if path.is_symlink():
            raise AppException("Arsip cadangan tidak tersedia.", 404)
        return path

    def available(self, backup) -> bool:
        return backup.status == "success" and self.path(backup.id).is_file()
