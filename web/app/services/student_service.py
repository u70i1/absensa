from enum import Enum

from app.models.class_ import Class
from app.models.student import Student
from app.schemas.student import StudentListQuery
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .exceptions import ClassNotFound, DuplicateNisn, StudentNotFound


class _Unchanged(Enum):
    VALUE = 0


def _save_student(db: Session, *, commit: bool) -> None:
    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "pgcode", None) == "23505":
            raise DuplicateNisn() from exc
        if getattr(exc.orig, "pgcode", None) == "23503":
            raise ClassNotFound() from exc
        raise


def _normalize_guardian_phone(value: str | None) -> str | None:
    """Store the already-validated, digits-only guardian number or NULL."""
    return value or None


def _student_filters(query: StudentListQuery):
    """Shared predicates for the JSON list, dashboard, and filtered count."""
    filters: list[ColumnElement[bool]] = []

    if query.name is not None:
        filters.append(Student.name.ilike(f"%{query.name}%"))
    if query.class_name is not None:
        filters.append(Class.class_name.ilike(f"%{query.class_name}%"))
    if query.nisn is not None:
        filters.append(Student.nisn == query.nisn)
    if query.grade is not None:
        filters.append(Class.grade == query.grade)
    if query.class_id is not None:
        filters.append(Student.class_id == query.class_id)
    if query.unassigned:
        filters.append(Student.class_id.is_(None))
    if query.q:
        filters.append(or_(Student.name.ilike(f"%{query.q}%"), Student.nisn == query.q))
    return filters


def count_students(db: Session, query: StudentListQuery) -> int:
    return (
        db.scalar(
            select(func.count(Student.id))
            .outerjoin(Class, Class.class_id == Student.class_id)
            .where(*_student_filters(query))
        )
        or 0
    )


def get_student_by_id(db: Session, student_id: int) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise StudentNotFound()
    return student


def _student_list_statement(query: StudentListQuery):
    return (
        select(
            Student.id,
            Student.name,
            Student.nisn,
            Student.current,
            Student.guardian_phone,
            Student.photo_path,
            Class.class_name,
            Class.class_id,
        )
        .outerjoin(Class, Class.class_id == Student.class_id)
        .where(*_student_filters(query))
        .order_by(Class.grade, Class.class_name, Student.name, Student.id)
    )


def get_student(db: Session, query: StudentListQuery):
    """Retrieve a page of students using the shared list filters."""
    stmt = (
        _student_list_statement(query)
        .offset((query.page - 1) * query.limit)
        .limit(query.limit)
    )
    return list(db.execute(stmt).all())


def get_students_for_export(
    db: Session,
    query: StudentListQuery,
    *,
    student_ids: list[int] | None = None,
    class_ids: list[int] | None = None,
):
    """Retrieve every student matching the list filters, without pagination."""
    statement = _student_list_statement(query)
    if student_ids is not None:
        statement = statement.where(Student.id.in_(student_ids))
    if class_ids is not None:
        statement = statement.where(Student.class_id.in_(class_ids))
    return list(db.execute(statement).all())


def post_student(
    db: Session,
    nisn: str,
    name: str,
    class_id: int | None,
    current: bool,
    guardian_phone: str | None = None,
    *,
    commit: bool = True,
) -> Student:
    """_summary_

    Raises:
        DuplicateNisn
        ClassNotFound

    Returns:
        Student: _Student from the database model_
    """
    nisn_exist = db.scalar(select(Student).where(Student.nisn == nisn))
    if nisn_exist:
        raise DuplicateNisn

    if class_id is not None:
        class_exist = db.get(Class, class_id)
        if not class_exist:
            raise ClassNotFound

    new_student = Student(
        name=name,
        nisn=nisn,
        class_id=class_id,
        current=current,
        guardian_phone=_normalize_guardian_phone(guardian_phone),
    )

    db.add(new_student)
    _save_student(db, commit=commit)

    return new_student


def edit_student(
    db: Session,
    student_id: int,
    nisn: str,
    name: str,
    class_id: int | None,
    current: bool,
    guardian_phone: str | None | _Unchanged = _Unchanged.VALUE,
    *,
    commit: bool = True,
) -> Student:
    """_Edit one student_

    Raises:
        StudentNotFound
        ClassNotFound
        DuplicateNisn

    Returns:
        Student: _Student model from the database_
    """
    to_update = get_student_by_id(db, student_id)

    if class_id is not None:
        class_exist = db.get(Class, class_id)
        if not class_exist:
            raise ClassNotFound()

    nisn_dupe_exists = db.scalar(
        select(Student).where(Student.id != student_id).where(Student.nisn == nisn)
    )
    if nisn_dupe_exists:
        raise DuplicateNisn()

    to_update.name = name
    to_update.class_id = class_id
    to_update.nisn = nisn
    to_update.current = current
    if not isinstance(guardian_phone, _Unchanged):
        to_update.guardian_phone = _normalize_guardian_phone(guardian_phone)

    _save_student(db, commit=commit)

    return to_update


def delete_student(db: Session, student_id: int):
    """_Delete a single student_

    Raises:
        StudentNotFound
    """
    to_delete = get_student_by_id(db, student_id)

    db.delete(to_delete)
    db.commit()
