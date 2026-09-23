"""Confirmation and submission for dashboard bulk selections."""
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.core.admin_auth import require_admin
from app.routes.admin import Db, list_query, mutation_success, render_modal
from app.routes.admin_classes import class_query, mutation_response
from app.services import table_selection_service as service
from app.services.exceptions import AppException

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.post("/{kind}/selection/{step}", name="admin_table_selection")
async def selection(kind: str, step: str, request: Request, db: Db):
    back_url = "/admin/classes" if kind == "classes" else "/admin/students"
    context = {"back_url": back_url, "back_label": "Kembali ke daftar"}
    try:
        if step not in {"confirm", "apply"}:
            raise AppException("Tindakan tidak valid.", 422)
        query = class_query(request) if kind == "classes" else list_query(request)
        form = await request.form()
        action, ids = form.get("action"), form.getlist("ids")
        if step == "apply":
            count = service.apply_selection(db, kind, action, ids)
            message = f"{count} data berhasil " + ("dinonaktifkan." if action == "deactivate" else "dihapus.")
            render = mutation_response if kind == "classes" else mutation_success
            return render(request, db, query, message)
        records = service.selected_records(db, kind, action, ids)
        return render_modal(request, "modals/table-selection.html", context | {
            "kind": kind, "action": action, "records": records,
            "verb": "Nonaktifkan" if action == "deactivate" else "Hapus",
            "noun": "siswa" if kind == "students" else "kelas",
        })
    except (AppException, ValidationError) as exc:
        return render_modal(request, "modals/message.html", context | {
            "title": "Pilihan tidak dapat diproses",
            "error": exc.detail if isinstance(exc, AppException) else "Filter tidak valid.",
        }, exc.status_code if isinstance(exc, AppException) else 422)
