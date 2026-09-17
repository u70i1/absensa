from app.models.class_ import Class
from app.models.student import Student
from app.schemas.student import StudentListQuery
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .exceptions import ClassNotFound, DuplicateNisn, StudentNotFound


def _normalize_guardian_phone(value: str | None) -> str | None:
    """Store the already-validated, digits-only guardian number or NULL."""
    return value or None


def _student_filters(query: StudentListQuery):
    """Shared predicates for the JSON list, dashboard, and filtered count."""
    filters = []

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


def get_student(db: Session, query: StudentListQuery):
    """Retrieve a page of students using the shared list filters."""

    stmt = (
        select(
            Student.id,
            Student.name,
            Student.nisn,
            Student.current,
            Student.guardian_phone,
            Class.class_name,
            Class.class_id,
        )
        .outerjoin(Class, Class.class_id == Student.class_id)
        .where(*_student_filters(query))
        .offset((query.page - 1) * query.limit)
        .limit(query.limit)
        .order_by(Student.name)
    )
    students = db.execute(stmt).all()

    results = list(students)

    return results


def post_student(
    db: Session,
    nisn: str,
    name: str,
    class_id: int | None,
    current: bool,
    guardian_phone: str | None = None,
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

    if class_id:
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
    db.commit()

    return new_student


def edit_student(
    db: Session,
    student_id: int,
    nisn: str,
    name: str,
    class_id: int | None,
    current: bool,
    guardian_phone: str | None = None,
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

    if class_id:
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
    to_update.guardian_phone = _normalize_guardian_phone(guardian_phone)

    db.commit()

    return to_update


def delete_student(db: Session, student_id: int):
    """_Delete a single student_

    Raises:
        StudentNotFound
    """
    to_delete = get_student_by_id(db, student_id)

    db.delete(to_delete)
    db.commit()
