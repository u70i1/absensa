"""Shared filtered student list context for administrator pages."""

from math import ceil
from urllib.parse import urlencode

from app.schemas.student import StudentListQuery
from app.services import class_service, student_service
from sqlalchemy.orm import Session

PAGE_SIZE = 50


def student_filter_summary(query: StudentListQuery, classes) -> str:
    """Describe the same student filters used by the dashboard and export."""
    filters = []
    if query.q:
        filters.append(f'Pencarian "{query.q}"')
    if query.name:
        filters.append(f'Nama "{query.name}"')
    if query.nisn:
        filters.append(f"NISN {query.nisn}")
    selected_class = next(
        (item for item in classes if item.class_id == query.class_id), None
    )
    if query.unassigned:
        filters.append("Tanpa kelas")
    elif selected_class:
        filters.append(
            f"Kelas {selected_class.class_name} (Jenjang {selected_class.grade})"
        )
    elif query.grade is not None:
        filters.append(f"Jenjang {query.grade}")
    if query.class_name:
        filters.append(f'Nama kelas "{query.class_name}"')
    return ", ".join(filters) or "Semua siswa"


def list_url(query: StudentListQuery, *, base_url="/admin/students", **changes) -> str:
    values = query.model_dump(by_alias=True, exclude={"limit"}) | changes
    values = {
        key: value
        for key, value in values.items()
        if value is not None and value != "" and value is not False
    }
    return f"{base_url}?{urlencode(values)}"


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


def dashboard_context(
    db: Session, query: StudentListQuery, *, base_url="/admin/students"
) -> dict:
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
        "list_url": lambda **changes: list_url(query, base_url=base_url, **changes),
    }
