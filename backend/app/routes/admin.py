"""Server-rendered student management; JSON and HTML share student services."""

from datetime import datetime
from math import ceil
from typing import Annotated
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.schemas.student import StudentListQuery, StudentWriteRequest
from app.services import class_service, export_service, student_service
from app.services.exceptions import AppException, StudentNotFound
from app.templating import templates
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/admin",
    default_response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
Db = Annotated[Session, Depends(get_db)]
PAGE_SIZE = 50
STUDENTS_URL = "/admin/students"
ERROR_MESSAGES = {
    "duplicate_nisn": "NISN sudah digunakan oleh siswa lain.",
    "class_not_found": "Kelas tidak ditemukan. Silakan pilih kelas yang tersedia.",
    "student_not_found": "Siswa tidak ditemukan. Data mungkin sudah dihapus.",
}


def list_query(request: Request) -> StudentListQuery:
    # The dashboard page size is product behavior, never a client preference.
    return StudentListQuery.model_validate({**request.query_params, "limit": PAGE_SIZE})


def list_url(query: StudentListQuery, **changes) -> str:
    values = query.model_dump(by_alias=True, exclude={"limit"}) | changes
    values = {
        key: value
        for key, value in values.items()
        if value is not None and value != "" and value is not False
    }
    return f"{STUDENTS_URL}?{urlencode(values)}"


def normalize_filters(db: Session, query: StudentListQuery):
    classes = class_service.get_class_options(db, query.grade)
    if query.unassigned:
        query = query.model_copy(
            update={"grade": None, "class_id": None, "class_name": None}
        )
        classes = []
    elif query.class_id is not None and not any(
        c.class_id == query.class_id for c in classes
    ):
        query = query.model_copy(update={"class_id": None, "page": 1})
    return query, classes


def dashboard_context(db: Session, query: StudentListQuery) -> dict:
    query, classes = normalize_filters(db, query)
    total = student_service.count_students(db, query)
    pages = max(1, ceil(total / PAGE_SIZE))
    if query.page > pages:
        query = query.model_copy(update={"page": 1})
    students = student_service.get_student(db, query)
    page_numbers = sorted(
        {
            1,
            pages,
            *range(max(1, query.page - 2), min(pages, query.page + 2) + 1),
        }
    )
    return {
        "query": query,
        "students": students,
        "total": total,
        "pages": pages,
        "page_numbers": page_numbers,
        "start": (query.page - 1) * PAGE_SIZE + 1 if total else 0,
        "end": min(query.page * PAGE_SIZE, total),
        "grades": class_service.get_student_grades(db),
        "classes": classes,
        "selected_class": next(
            (c for c in classes if c.class_id == query.class_id), None
        ),
        "list_url": lambda **changes: list_url(query, **changes),
    }


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
        name="tables/student-results.html" if fragment else "main-dashboard.html",
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
        name=template if fragment else "student-dialog.html",
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
    selected_class = next(
        (class_ for class_ in classes if class_.class_id == query.class_id), None
    )
    filters = []
    if query.q:
        filters.append(f'Pencarian "{query.q}"')
    if query.unassigned:
        filters.append("Tanpa kelas")
    elif selected_class:
        filters.append(f"Kelas {selected_class.class_name}")
    elif query.grade is not None:
        filters.append(f"Jenjang {query.grade}")
    elif query.class_name:
        filters.append(f'Nama kelas "{query.class_name}"')

    students = student_service.get_students_for_export(db, query)
    content = export_service.build_students_workbook(
        students, ", ".join(filters) or "Semua siswa"
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


async def form_data(request: Request) -> dict:
    return dict(await request.form())


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
