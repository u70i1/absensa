"""Class dashboard HTML routes using the existing class services."""

from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.routes.admin import Db, form_data, render_modal
from app.schemas.class_ import ClassListQuery, ClassWriteRequest
from app.services import class_service, export_service
from app.services.exceptions import AppException
from app.templating import templates
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

router = APIRouter(
    prefix="/admin/classes",
    default_response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)


def class_query(request: Request) -> ClassListQuery:
    values = dict(request.query_params)
    if values.get("grade") == "":
        values.pop("grade")
    return ClassListQuery.model_validate(values)


def directory_url(query: ClassListQuery) -> str:
    values = query.model_dump(
        by_alias=True, exclude={"page", "limit"}, exclude_none=True, exclude_defaults=True
    )
    return "/admin/classes" + (f"?{urlencode(values)}" if values else "")


def modal_response(request, template, context, status_code=200):
    return render_modal(request, template, context | {
        "back_url": "/admin/classes", "back_label": "Kembali ke daftar kelas",
        "dialog_title": "Kelas",
    }, status_code)


def class_error(request, exc):
    return modal_response(request, "modals/message.html", {
        "title": "Permintaan kelas gagal",
        "error": {"class_not_found": "Kelas tidak ditemukan.",
                  "duplicate_class": "Nama kelas sudah digunakan pada jenjang ini."}.get(
                      exc.detail, exc.detail),
    }, exc.status_code)


def invalid_filters(request):
    return modal_response(request, "modals/message.html", {
        "title": "Filter tidak valid", "error": "Periksa nilai jenjang pada alamat halaman.",
    }, 422)


def render_directory(request, db, query, message=None):
    fragment = request.headers.get("HX-Request") == "true" and request.headers.get(
        "HX-History-Restore-Request") != "true"
    response = templates.TemplateResponse(
        request=request,
        name="tables/class-results.html" if fragment else "class-dashboard.html",
        context={"query": query, "classes": class_service.get_class_directory(
            db, query.class_name, query.grade, query.empty), "summary": class_service.get_class_summary(db),
            "grades": class_service.get_class_grades(db), "message": message,
            "filter_query": urlencode(query.model_dump(
                by_alias=True, exclude={"page", "limit"}, exclude_none=True,
                exclude_defaults=True))},
    )
    response.headers["Vary"] = "HX-Request, HX-History-Restore-Request"
    if fragment:
        response.headers["HX-Push-Url"] = directory_url(query)
    return response


@router.get("", name="admin_classes")
def classes(request: Request, db: Db):
    try:
        query = class_query(request)
    except ValidationError:
        return invalid_filters(request)
    return render_directory(request, db, query)


@router.get("/export", name="admin_classes_export")
def export_classes(request: Request, db: Db):
    try:
        query = class_query(request)
    except ValidationError:
        return invalid_filters(request)
    filters = []
    if query.class_name:
        filters.append(f'Pencarian "{query.class_name}"')
    if query.grade is not None:
        filters.append(f"Jenjang {query.grade}")
    if query.empty:
        filters.append("Kelas kosong")
    content = export_service.build_classes_workbook(
        class_service.get_class_directory(db, query.class_name, query.grade, query.empty),
        ", ".join(filters) or "Semua kelas",
    )
    filename = datetime.now(ZoneInfo(settings.timezone)).strftime("ekspor-kelas-%Y-%m-%d.xlsx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


def form_response(request, class_=None, values=None, errors=None, status_code=200):
    return modal_response(request, "modals/class-form.html", {
        "class_": class_, "values": values if values is not None else (
            {"class_name": class_.class_name, "grade": class_.grade} if class_ else {}),
        "errors": errors or {},
    }, status_code)


@router.get("/new", name="admin_class_new")
def new_class(request: Request):
    return form_response(request)


@router.get("/{class_id:int}/edit", name="admin_class_edit")
def edit_class(class_id: int, request: Request, db: Db):
    try:
        return form_response(request, class_service.get_class_by_id(db, class_id))
    except AppException as exc:
        return class_error(request, exc)


def mutation_response(request, db, query, message):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(directory_url(query), status_code=303)
    response = render_directory(request, db, query, message)
    response.headers.update({"HX-Retarget": "#class-results", "HX-Reswap": "outerHTML",
                             "HX-Trigger-After-Swap": "classSaved"})
    return response


def save_class(request, db, data, class_id=None):
    try:
        query = class_query(request)
    except ValidationError:
        return invalid_filters(request)
    try:
        class_ = class_service.get_class_by_id(db, class_id) if class_id is not None else None
    except AppException as exc:
        return class_error(request, exc)
    values = {key: data.get(key) for key in ("class_name", "grade")}
    try:
        payload = ClassWriteRequest.model_validate(values)
    except ValidationError as exc:
        errors = {str(error["loc"][0]): {
            "class_name": "Nama kelas wajib diisi, maksimal 20 karakter.",
            "grade": "Jenjang harus berupa angka 1–20.",
        }.get(str(error["loc"][0]), "Nilai tidak valid.") for error in exc.errors()}
        return form_response(request, class_, values, errors, 422)
    try:
        if class_id is None:
            class_service.post_class(db, **payload.model_dump())
        else:
            class_service.update_class(db, class_id, **payload.model_dump())
    except AppException as exc:
        return form_response(request, class_, values, {"form":
            "Nama kelas sudah digunakan pada jenjang ini." if exc.detail == "duplicate_class"
            else exc.detail}, exc.status_code)
    return mutation_response(request, db, query, "Data kelas berhasil disimpan.")


@router.post("", name="admin_class_create")
def create_class(request: Request, db: Db, data: dict = Depends(form_data)):
    return save_class(request, db, data)


@router.post("/{class_id:int}/edit", name="admin_class_update")
def update_class(class_id: int, request: Request, db: Db, data: dict = Depends(form_data)):
    return save_class(request, db, data, class_id)


@router.get("/{class_id:int}/delete", name="admin_class_delete_confirmation")
def confirm_delete(class_id: int, request: Request, db: Db):
    try:
        class_ = class_service.get_class_by_id(db, class_id)
    except AppException as exc:
        return class_error(request, exc)
    return modal_response(request, "modals/class-delete.html", {"class_": class_})


@router.post("/{class_id:int}/delete", name="admin_class_delete")
def delete_class(class_id: int, request: Request, db: Db):
    try:
        query = class_query(request)
    except ValidationError:
        return invalid_filters(request)
    try:
        class_service.delete_class(db, class_id)
    except AppException as exc:
        return class_error(request, exc)
    return mutation_response(request, db, query, "Kelas berhasil dihapus.")
