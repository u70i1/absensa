"""Confirmation and submission for dashboard bulk selections."""

from app.core.admin_auth import require_admin
from app.routes.admin import (
    Db,
    list_query,
    mutation_success,
    render_modal,
    students_export_response,
)
from app.routes.admin_classes import (
    class_filter_summary,
    class_query,
    mutation_response,
)
from app.routes.admin_scans import LOCAL_TZ, scan_query
from app.routes.admin_scans import mutation_response as scan_mutation_response
from app.services import class_service
from app.services import table_selection_service as service
from app.services.exceptions import AppException
from app.services.student_dashboard_service import (
    normalize_filters,
    student_filter_summary,
)
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.post("/{kind}/selection/{step}", name="admin_table_selection")
async def selection(kind: str, step: str, request: Request, db: Db):
    back_url = (
        f"/admin/{kind}"
        if kind in {"students", "classes", "scans"}
        else "/admin/students"
    )
    context = {
        "back_url": back_url + (f"?{request.url.query}" if request.url.query else ""),
        "back_label": "Kembali ke daftar",
    }
    try:
        if kind not in {"students", "classes", "scans"}:
            raise AppException("Daftar tidak ditemukan.", 404)
        if step not in {"confirm", "apply", "export"}:
            raise AppException("Tindakan tidak valid.", 422)
        query = (
            class_query(request)
            if kind == "classes"
            else scan_query(request)
            if kind == "scans"
            else list_query(request)
        )
        form = await request.form(max_files=0, max_fields=1001)
        action, ids = form.get("action"), form.getlist("ids")
        if step == "export" and action != "export":
            raise AppException("Tindakan tidak valid.", 422)
        if action == "export" and step in {"confirm", "export"}:
            records, students, scope = service.selection_export_data(db, kind, ids)
            if kind == "students":
                query, classes = normalize_filters(db, query)
                filters = student_filter_summary(query, classes)
            else:
                filters = class_filter_summary(query)
            if step == "export":
                return await run_in_threadpool(
                    students_export_response,
                    db,
                    students,
                    f"{scope}; Filter daftar: {filters}",
                )
            return render_modal(
                request,
                "modals/export-confirm.html",
                context
                | {
                    "export_count": len(students),
                    "selection_kind": kind,
                    "selected_records": records,
                    "selection_count": len(records),
                    "filter_summary": filters,
                    "scope": scope
                    if kind == "students"
                    else f"Siswa dari {len(records)} kelas terpilih",
                    "directory_class_count": len(class_service.get_class_options(db)),
                    "download_url": str(
                        request.url_for(
                            "admin_table_selection", kind=kind, step="export"
                        )
                    )
                    + (f"?{request.url.query}" if request.url.query else ""),
                    "download_method": "post",
                    "download_fields": [("action", "export")]
                    + [
                        ("ids", record.id if kind == "students" else record.class_id)
                        for record in records
                    ],
                },
            )
        if step == "apply":
            count = service.apply_selection(db, kind, action, ids)
            result = "dinonaktifkan" if action == "deactivate" else "dihapus"
            message = f"{count} data berhasil {result}."
            render = (
                mutation_response
                if kind == "classes"
                else scan_mutation_response
                if kind == "scans"
                else mutation_success
            )
            return render(request, db, query, message)
        records = service.selected_records(db, kind, action, ids)
        return render_modal(
            request,
            "modals/table-selection.html",
            context
            | {
                "kind": kind,
                "action": action,
                "records": records,
                "verb": "Nonaktifkan" if action == "deactivate" else "Hapus",
                "noun": {
                    "students": "siswa",
                    "classes": "kelas",
                    "scans": "log presensi",
                }[kind],
                "scan_timezone": LOCAL_TZ,
            },
        )
    except (AppException, ValidationError) as exc:
        return render_modal(
            request,
            "modals/message.html",
            context
            | {
                "title": "Pilihan tidak dapat diproses",
                "error": exc.detail
                if isinstance(exc, AppException)
                else "Filter tidak valid.",
            },
            exc.status_code if isinstance(exc, AppException) else 422,
        )
