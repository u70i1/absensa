"""Administrator-only backup service endpoints; request handlers only enqueue."""

from datetime import UTC, datetime
from math import ceil
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.backup import Backup
from app.routes.admin import render_modal
from app.services import backup_service as backups
from app.services.backup_crypto_service import encryption_key
from app.services.backup_storage_service import LocalBackupStorage
from app.services.exceptions import AppException
from app.templating import templates
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin/backups", dependencies=[Depends(require_admin)])
Database = Annotated[Session, Depends(get_db)]
PAGE_SIZE = 25
STATUS_LABELS = {
    "queued": "Dalam antrean",
    "running": "Sedang dibuat",
    "success": "Berhasil",
    "failed": "Gagal",
    "expired": "Dihapus oleh retensi",
}
PHASE_LABELS = {
    "queued": "Menunggu pekerja cadangan",
    "archiving": "Menyalin database dan berkas",
    "local_complete": "Salinan lokal selesai",
    "complete": "Selesai",
    "failed": "Pembuatan terhenti",
    "expired": "Arsip telah dihapus",
}


def local_time(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone(ZoneInfo(settings.timezone)).strftime("%d/%m/%Y %H:%M:%S")


def file_size(value: int | None) -> str:
    if value is None:
        return "—"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "—"


def page_context(db: Session, page: int) -> dict:
    config = backups.get_settings(db)
    storage = LocalBackupStorage()
    total = db.scalar(select(func.count()).select_from(Backup)) or 0
    pages = max(1, ceil(total / PAGE_SIZE))
    page = min(page, pages)
    rows = list(
        db.scalars(
            select(Backup)
            .order_by(Backup.created_at.desc(), Backup.id.desc())
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
    )
    latest = db.scalar(
        select(Backup).order_by(Backup.created_at.desc(), Backup.id.desc()).limit(1)
    )
    active = db.scalar(
        select(Backup)
        .where(Backup.status.in_(backups.ACTIVE))
        .order_by(Backup.created_at.desc())
        .limit(1)
    )
    successful = list(
        db.scalars(
            select(Backup)
            .where(Backup.status == "success")
            .order_by(Backup.created_at.desc())
        )
    )
    usable = next((b for b in successful if storage.available(b)), None)
    ready_error = None
    try:
        encryption_key()
    except AppException as exc:
        ready_error = exc.detail
    running = active is not None and active.status != "queued"
    stale = config.worker_seen_at is None or (
        datetime.now(UTC) - config.worker_seen_at
    ).total_seconds() > (settings.backup_timeout_seconds + 120 if running else 60)
    return {
        "config": config,
        "rows": rows,
        "latest": latest,
        "usable": usable,
        "active": active,
        "page": page,
        "pages": pages,
        "total": total,
        "local_available": storage.available,
        "local_time": local_time,
        "file_size": file_size,
        "status_labels": STATUS_LABELS,
        "phase_labels": PHASE_LABELS,
        "timezone": settings.timezone,
        "ready_error": ready_error,
        "worker_stale": stale,
        "recovery_stale": usable is not None
        and (datetime.now(UTC) - usable.created_at).total_seconds() > 86400,
    }


def render_page(
    request: Request,
    db: Session,
    page: int = 1,
    *,
    error=None,
    status_code=200,
    form_values=None,
):
    context = page_context(db, page)
    context.update(error=error, form_values=form_values)
    context["notice"] = {
        "queued": "Cadangan masuk antrean. Status diperbarui otomatis.",
        "settings": "Pengaturan cadangan disimpan.",
    }.get(request.query_params.get("notice"))
    fragment = request.headers.get("HX-Request") == "true" and error is None
    response = templates.TemplateResponse(
        request=request,
        name="admin/components/backup-results.html"
        if fragment
        else "admin/pages/backups.html",
        context=context,
        status_code=status_code,
    )
    response.headers["Vary"] = "HX-Request"
    if fragment and request.url.path == "/admin/backups":
        response.headers["HX-Push-Url"] = f"/admin/backups?page={context['page']}"
    return response


@router.get("", name="admin_backups")
def dashboard(request: Request, db: Database, page: int = Query(1, ge=1, le=1000000)):
    return render_page(request, db, page)


@router.get("/status", name="admin_backups_status")
def status_fragment(
    request: Request, db: Database, page: int = Query(1, ge=1, le=1000000)
):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(f"/admin/backups?page={page}", status_code=303)
    return render_page(request, db, page)


@router.get("/confirm", name="admin_backups_confirmation")
def confirmation(request: Request, db: Database):
    try:
        encryption_key()
    except AppException as exc:
        return render_modal(
            request,
            "modals/message.html",
            {
                "title": "Cadangan belum siap",
                "error": exc.detail,
                "back_url": "/admin/backups",
                "dialog_title": "Cadangan",
            },
            exc.status_code,
        )
    return render_modal(
        request,
        "modals/backup-confirm.html",
        {
            "back_url": "/admin/backups",
            "back_label": "Kembali ke cadangan",
            "dialog_title": "Konfirmasi cadangan",
            "active": backups.active_backup(db),
        },
    )


@router.post("/manual", name="admin_backups_manual")
def manual(request: Request, db: Database):
    try:
        backups.enqueue(db)
    except AppException as exc:
        return render_page(request, db, error=exc.detail, status_code=exc.status_code)
    return RedirectResponse("/admin/backups?notice=queued", status_code=303)


@router.post("/settings", name="admin_backups_settings")
def update_settings(
    request: Request,
    db: Database,
    time_one: str = Form(..., max_length=5),
    time_two: str = Form("", max_length=5),
    daily: int = Form(...),
    weekly: int = Form(...),
    monthly: int = Form(...),
    enabled: bool = Form(False),
):
    values = SimpleNamespace(
        time_one=time_one,
        time_two=time_two,
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        enabled=enabled,
    )
    try:
        backups.update_settings(
            db,
            enabled=enabled,
            times=",".join(t for t in (time_one, time_two) if t),
            daily=daily,
            weekly=weekly,
            monthly=monthly,
        )
    except AppException as exc:
        return render_page(
            request,
            db,
            error=exc.detail,
            status_code=exc.status_code,
            form_values=values,
        )
    return RedirectResponse("/admin/backups?notice=settings", status_code=303)


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
        "integrity_error": backup.integrity_error,
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
