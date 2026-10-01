"""Server-rendered student management; JSON and HTML share student services."""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.schemas.student import StudentListQuery, StudentWriteRequest
from app.services import (
    class_service,
    export_service,
    student_photo_service,
    student_service,
)
from app.services.exceptions import AppException, StudentNotFound
from app.services.student_dashboard_service import (
    PAGE_SIZE,
    dashboard_context,
    list_url,
    normalize_filters,
    student_filter_summary,
)
from app.templating import templates
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

router = APIRouter(
    prefix="/admin",
    default_response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
Db = Annotated[Session, Depends(get_db)]
STUDENTS_URL = "/admin/students"
ERROR_MESSAGES = {
    "duplicate_nisn": "NISN sudah digunakan oleh siswa lain.",
    "class_not_found": "Kelas tidak ditemukan. Silakan pilih kelas yang tersedia.",
    "student_not_found": "Siswa tidak ditemukan. Data mungkin sudah dihapus.",
}


def list_query(request: Request) -> StudentListQuery:
    # The dashboard page size is product behavior, never a client preference.
    return StudentListQuery.model_validate({**request.query_params, "limit": PAGE_SIZE})


def render_dashboard(
    request: Request, db: Session, query: StudentListQuery, message=None
):
    context = dashboard_context(db, query) | {"message": message}
    fragment = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )
    response = templates.TemplateResponse(
        request=request,
        name="tables/student-results.html" if fragment else "admin/pages/students.html",
        context=context,
    )
    response.headers["Vary"] = "HX-Request, HX-History-Restore-Request"
    if fragment:
        response.headers["HX-Push-Url"] = list_url(context["query"])  # type: ignore
    return response


def render_modal(request: Request, template: str, context: dict, status_code=200):
    fragment = request.headers.get("HX-Request") == "true"
    response = templates.TemplateResponse(
        request=request,
        name=template if fragment else "admin/pages/student-dialog.html",
        context=context | {"modal_template": template},
        status_code=status_code,
    )
    if fragment:
        response.headers["HX-Retarget"] = "#modal-content"
        response.headers["HX-Reswap"] = "innerHTML"
        response.headers["X-Admin-Fragment"] = "modal"
    return response


def query_error(request: Request):
    return render_modal(
        request,
        "modals/message.html",
        {
            "title": "Filter tidak valid",
            "error": "Periksa nilai halaman, jenjang, dan kelas pada alamat halaman.",
        },
        422,
    )


@router.get("/students", name="admin_students")
def students(request: Request, db: Db):
    try:
        query = list_query(request)
    except ValidationError:
        return query_error(request)
    return render_dashboard(request, db, query)


@router.get("/students/export", name="admin_students_export")
def export_students(request: Request, db: Db):
    try:
        query = list_query(request)
    except ValidationError:
        return query_error(request)
    query, classes = normalize_filters(db, query)
    students = student_service.get_students_for_export(db, query)
    return students_export_response(
        db, students, student_filter_summary(query, classes)
    )


@router.get("/students/export/confirm", name="admin_students_export_confirm")
def confirm_student_export(request: Request, db: Db):
    try:
        query = list_query(request)
    except ValidationError:
        return query_error(request)
    query, classes = normalize_filters(db, query)
    return render_modal(
        request,
        "modals/export-confirm.html",
        {
            "back_url": list_url(query),
            "export_count": student_service.count_students(db, query),
            "filter_summary": student_filter_summary(query, classes),
            "scope": "Semua siswa sesuai filter, termasuk halaman lainnya",
            "directory_class_count": len(class_service.get_class_options(db)),
            "download_url": request.url_for("admin_students_export"),
            "download_method": "get",
            "download_fields": query.model_dump(
                by_alias=True,
                exclude={"page", "limit"},
                exclude_none=True,
                exclude_defaults=True,
            ).items(),
        },
    )


def students_export_response(db: Session, students, filter_summary: str):
    """Use the combined workbook for filtered and selected dashboard exports."""
    content = export_service.build_students_workbook(
        students,
        filter_summary,
        class_service.get_class_options(db),
    )
    filename = datetime.now(ZoneInfo(settings.timezone)).strftime(
        "ekspor-siswa-%Y-%m-%d.xlsx"
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def form_context(db: Session, student=None, values=None, errors=None) -> dict:
    return {
        "student": student,
        "values": values
        if values is not None
        else (
            StudentWriteRequest.model_validate(
                student, from_attributes=True
            ).model_dump()
            if student
            else {"name": "", "nisn": "", "class_id": None, "current": True}
        ),
        "classes": class_service.get_class_options(db),
        "errors": errors or {},
    }


@router.get("/students/new", name="admin_student_new")
def new_student(request: Request, db: Db):
    return render_modal(request, "modals/student-form.html", form_context(db))


def missing_student(request: Request, status_code=404):
    return render_modal(
        request,
        "modals/message.html",
        {
            "title": "Siswa tidak ditemukan",
            "error": ERROR_MESSAGES["student_not_found"],
        },
        status_code,
    )


@router.get("/students/{student_id:int}", name="admin_student_detail")
def student_detail(student_id: int, request: Request, db: Db):
    try:
        student = student_service.get_student_by_id(db, student_id)
    except StudentNotFound:
        return missing_student(request)
    return render_modal(request, "modals/student-detail.html", {"student": student})


@router.get("/students/{student_id:int}/edit", name="admin_student_edit")
def edit_student(student_id: int, request: Request, db: Db):
    try:
        student = student_service.get_student_by_id(db, student_id)
    except StudentNotFound:
        return missing_student(request)
    return render_modal(request, "modals/student-form.html", form_context(db, student))


async def form_data(request: Request) -> AsyncIterator[dict]:
    async with request.form() as form:
        yield dict(form)


def mutation_success(
    request: Request, db: Session, query: StudentListQuery, message: str
):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(list_url(query), status_code=303)
    response = render_dashboard(request, db, query, message)
    response.headers["HX-Retarget"] = "#student-results"
    response.headers["HX-Reswap"] = "outerHTML"
    response.headers["HX-Trigger-After-Swap"] = "studentSaved"
    return response


def save_student(
    request: Request, db: Session, data: dict, student_id: int | None = None
):
    try:
        query = list_query(request)
    except ValidationError:
        return query_error(request)
    student = None
    if student_id is not None:
        try:
            student = student_service.get_student_by_id(db, student_id)
        except StudentNotFound:
            return missing_student(request, 422)
    values = {
        key: data.get(key)
        for key in ("name", "nisn", "class_id", "current", "guardian_phone")
    }
    values["class_id"] = values["class_id"] or None
    values["guardian_phone"] = values["guardian_phone"] or None
    errors = {}
    try:
        payload = StudentWriteRequest.model_validate(values)
    except ValidationError as exc:
        for error in exc.errors():
            field = str(error["loc"][0])
            errors[field] = {
                "nisn": "NISN harus terdiri dari tepat 10 karakter.",
                "name": "Nama siswa wajib diisi.",
                "class_id": "Pilih kelas yang valid.",
                "current": "Pilih status siswa yang valid.",
            }.get(field, "Nilai tidak valid.")
        return render_modal(
            request,
            "modals/student-form.html",
            form_context(db, student, values, errors),
            422,
        )
    try:
        if student_id is None:
            photo = data.get("photo")
            if isinstance(photo, UploadFile) and photo.filename:
                student_photo_service.create_student_with_photo(
                    db, photo.file, **payload.model_dump()
                )
            else:
                student_service.post_student(db, **payload.model_dump())
        else:
            student_service.edit_student(db, student_id, **payload.model_dump())
    except AppException as exc:
        errors["form"] = ERROR_MESSAGES.get(exc.detail, exc.detail)
        return render_modal(
            request,
            "modals/student-form.html",
            form_context(db, student, values, errors),
            exc.status_code,
        )
    return mutation_success(request, db, query, "Data siswa berhasil disimpan.")


@router.post("/students", name="admin_student_create")
def create_student(request: Request, db: Db, data: Annotated[dict, Depends(form_data)]):
    return save_student(request, db, data)


@router.post("/students/{student_id:int}/edit", name="admin_student_update")
def update_student(
    student_id: int,
    request: Request,
    db: Db,
    data: Annotated[dict, Depends(form_data)],
):
    return save_student(request, db, data, student_id)


@router.get(
    "/students/{student_id:int}/delete", name="admin_student_delete_confirmation"
)
def confirm_delete(student_id: int, request: Request, db: Db):
    try:
        student = student_service.get_student_by_id(db, student_id)
    except StudentNotFound:
        return missing_student(request)
    return render_modal(request, "modals/student-delete.html", {"student": student})


@router.post("/students/{student_id:int}/delete", name="admin_student_delete")
def delete_student(student_id: int, request: Request, db: Db):
    try:
        query = list_query(request)
    except ValidationError:
        return query_error(request)
    try:
        student_service.delete_student(db, student_id)
    except AppException as exc:
        return render_modal(
            request,
            "modals/message.html",
            {
                "title": "Siswa tidak dapat dihapus",
                "error": ERROR_MESSAGES.get(exc.detail, exc.detail),
            },
            exc.status_code,
        )
    return mutation_success(request, db, query, "Siswa berhasil dihapus.")
