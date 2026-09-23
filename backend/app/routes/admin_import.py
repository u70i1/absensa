"""Admin import pages; parsing and writes belong to the import service."""

from typing import Annotated, Literal

from app.core.admin_auth import CurrentAdmin, require_admin
from app.db.session import get_db
from app.models.class_ import Class
from app.services import export_service, import_service
from app.services.exceptions import AppException
from app.templating import templates
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

router = APIRouter(prefix="/admin/import", dependencies=[Depends(require_admin)])
Db = Annotated[Session, Depends(get_db)]
Kind = Literal["students", "classes"]


def render_import(request, batch=None, error=None, status_code=200, selected_rows=None, *, fragment=False):
    rows = batch.payload.get("rows", []) if batch else []
    groups = [
        {"kind": kind, "label": label, "rows": [row for row in rows if row.get("kind", batch.kind) == kind]}
        for kind, label in (("students", "Siswa"), ("classes", "Kelas"))
    ] if batch else []
    response = templates.TemplateResponse(
        request=request, name="tables/import-review.html" if fragment else "import-dashboard.html",
        context={"batch": batch, "error": error, "selected_rows": selected_rows, "review_groups": groups}, status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def render_row_editor(request, db, batch, row, *, values=None, error=None, status_code=200, revision=None):
    if values is None:
        values = dict(row["values"])
        if "current" in values:
            values["current"] = "Aktif" if values["current"] else "Tidak aktif"
    response = templates.TemplateResponse(
        request=request, name="modals/import-row-form.html",
        context={"batch": batch, "row": row, "values": values, "error": error,
                 "revision": row.get("revision", 0) if revision is None else revision,
                 "kind": row.get("kind", batch.kind),
                 "classes": list(db.scalars(select(Class).order_by(Class.grade, Class.class_name)))},
        status_code=status_code,
    )
    response.headers.update({"Cache-Control": "no-store", "X-Admin-Fragment": "modal"})
    return response


@router.get("/{token}/rows/{key}/edit", name="admin_import_row_edit")
def edit_import_row(request: Request, token: str, key: int, db: Db, admin: CurrentAdmin):
    batch, row = import_service.get_editable_row(db, admin.id, token, key)
    return render_row_editor(request, db, batch, row)


@router.post("/{token}/rows/{key}/edit", name="admin_import_row_update")
def update_import_row(
    request: Request, token: str, key: int, db: Db, admin: CurrentAdmin,
    revision: Annotated[int, Form()],
    name: Annotated[str, Form()] = "", nisn: Annotated[str, Form()] = "",
    class_id: Annotated[str, Form()] = "", current: Annotated[str, Form()] = "",
    guardian_phone: Annotated[str, Form()] = "", grade: Annotated[str, Form()] = "",
    class_name: Annotated[str, Form()] = "", selected: Annotated[list[int], Form()] = [],
):
    values = dict(name=name, nisn=nisn, class_id=class_id, current=current,
                  guardian_phone=guardian_phone, grade=grade, class_name=class_name)
    try:
        batch = import_service.edit_preview_row(db, admin.id, token, key, values, revision)
    except AppException as exc:
        db.rollback()
        batch, row = import_service.get_editable_row(db, admin.id, token, key)
        return render_row_editor(request, db, batch, row, values=values, error=exc.detail,
                                 status_code=exc.status_code, revision=revision)
    response = render_import(request, batch, selected_rows=selected, fragment=True)
    response.headers.update({"HX-Retarget": "#import-review", "HX-Reswap": "outerHTML",
                             "HX-Trigger-After-Swap": "importRowSaved"})
    return response


@router.get("", name="admin_import")
def import_page(request: Request, db: Db, admin: CurrentAdmin, batch: str | None = None):
    try:
        preview = import_service.get_preview(db, admin.id, batch) if batch else None
        return render_import(request, preview)
    except AppException as exc:
        return render_import(request, error=exc.detail, status_code=exc.status_code)


@router.get("/template/{kind}", name="admin_import_template")
def import_template(kind: Kind):
    builder = export_service.build_students_workbook if kind == "students" else export_service.build_classes_workbook
    label = "siswa" if kind == "students" else "kelas"
    return Response(
        builder([], "Template kosong untuk impor"),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="template-{label}.xlsx"', "Cache-Control": "no-store"},
    )


@router.post("/preview", name="admin_import_preview")
@router.post("/preview/{kind}", name="admin_import_preview_legacy", include_in_schema=False)
async def preview_import(request: Request, db: Db, admin: CurrentAdmin, kind: Kind | None = None):
    try:
        async with request.form(max_files=1, max_fields=2) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise AppException("Pilih satu file Excel atau arsip terlebih dahulu.", 422)
            batch = await run_in_threadpool(import_service.create_preview, db, admin.id, kind, file.filename or "", file.file)
        return RedirectResponse(f"/admin/import?batch={batch.token}#import-review", status_code=303)
    except (AppException, HTTPException) as exc:
        message = exc.detail if isinstance(exc, AppException) else "Unggah tepat satu file Excel atau arsip."
        return render_import(request, error=message, status_code=exc.status_code)


@router.get("/{token}/photos/{nisn}", name="admin_import_photo")
def preview_photo(token: str, nisn: str, db: Db, admin: CurrentAdmin):
    return Response(
        import_service.get_preview_photo(db, admin.id, token, nisn),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{token}/confirm", name="admin_import_confirm")
def confirm_import(request: Request, token: str, db: Db, admin: CurrentAdmin, selected: Annotated[list[int], Form()] = []):
    try:
        import_service.apply_preview(db, admin.id, token, selected)
        return RedirectResponse(f"/admin/import?batch={token}#import-review", status_code=303)
    except AppException as exc:
        try:
            batch = import_service.get_preview(db, admin.id, token)
        except AppException:
            batch = None
        return render_import(request, batch, exc.detail, exc.status_code, selected_rows=selected)


@router.post("/{token}/cancel", name="admin_import_cancel")
def cancel_import(request: Request, token: str, db: Db, admin: CurrentAdmin):
    try:
        import_service.cancel_preview(db, admin.id, token)
        return RedirectResponse("/admin/import", status_code=303)
    except AppException as exc:
        return render_import(request, error=exc.detail, status_code=exc.status_code)
