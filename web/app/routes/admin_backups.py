"""Administrator-only backup service endpoints; request handlers only enqueue."""

from typing import Annotated
from uuid import UUID

from app.core.admin_auth import require_admin
from app.db.session import get_db
from app.models.backup import Backup
from app.services import backup_service as backups
from app.services.backup_storage_service import LocalBackupStorage
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin/backups", dependencies=[Depends(require_admin)])
Database = Annotated[Session, Depends(get_db)]


def backup_json(backup: Backup) -> dict:
    return {
        "id": backup.id,
        "created_at": backup.created_at,
        "finished_at": backup.finished_at,
        "type": backup.kind,
        "status": backup.status,
        "phase": backup.phase,
        "size": backup.size,
        "error": backup.error,
        "local_available": LocalBackupStorage().available(backup),
        "retention_error": backup.retention_error,
    }


@router.get("/api", name="admin_backups_api")
def inventory(db: Database):
    return [
        backup_json(b)
        for b in db.scalars(
            select(Backup).order_by(Backup.created_at.desc()).limit(200)
        )
    ]


@router.post("/api", status_code=202, name="admin_backups_enqueue")
def enqueue(db: Database):
    return backup_json(backups.enqueue(db))


@router.get("/{backup_id}/download", name="admin_backups_download")
def download(backup_id: UUID, db: Database):
    backup = db.get(Backup, backup_id.hex)
    storage = LocalBackupStorage()
    if backup is None or not storage.available(backup):
        raise HTTPException(404, "Arsip cadangan tidak tersedia.")
    return FileResponse(
        storage.path(backup.id),
        media_type="application/octet-stream",
        filename=f"absensa-{backup.created_at.strftime('%Y%m%d-%H%M%S')}-{backup.id}.absbackup",
    )
