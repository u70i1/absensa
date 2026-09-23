from app.models.class_ import Class
from app.models.student import Student
from app.schemas.student import ClassStudentListQuery
from app.services.exceptions import ClassNotFound, DuplicateClass
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def get_student_grades(db: Session) -> list[int]:
    """Only grades represented by students, ordered for the Jenjang filter."""
    return list(
        db.scalars(
            select(Class.grade)
            .join(Student, Student.class_id == Class.class_id)
            .distinct()
            .order_by(Class.grade)
        )
    )


def get_class_options(db: Session, grade: int | None = None) -> list[Class]:
    """Unpaginated class choices for filters and student forms."""
    stmt = select(Class).order_by(Class.grade, Class.class_name, Class.class_id)
    if grade is not None:
        stmt = stmt.where(Class.grade == grade)
    return list(db.scalars(stmt))


def get_classes(
    db: Session, class_name: str, limit: int, page: int, grade: int | None = None,
    empty: bool = False,
):
    filters = _class_filters(class_name, grade, empty)

    classes = db.scalars(
        select(Class)
        .where(*filters)
        .offset((page - 1) * limit)
        .limit(limit)
        .order_by(Class.class_id.desc())
    ).all()

    return list(classes)


def _class_filters(class_name: str | None, grade: int | None, empty: bool = False):
    filters = []

    if class_name is not None:
        filters.append(Class.class_name.ilike(f"%{class_name}%"))
    if grade is not None:
        filters.append(Class.grade == grade)
    if empty:
        filters.append(~Class.students.any())

    return filters


def get_class_directory(
    db: Session, class_name: str | None, grade: int | None, empty: bool = False
):
    """Scrollable class directory, including classes with no students."""
    return db.execute(
        select(Class.class_id, Class.class_name, Class.grade,
               func.count(Student.id).label("student_count"))
        .outerjoin(Student, Student.class_id == Class.class_id)
        .where(*_class_filters(class_name, grade, empty))
        .group_by(Class.class_id)
        .order_by(Class.class_id)
    ).all()


def get_class_summary(db: Session) -> dict:
    total_classes = db.scalar(select(func.count(Class.class_id))) or 0
    occupied = db.scalar(select(func.count(func.distinct(Student.class_id)))) or 0
    total_students, assigned = db.execute(
        select(func.count(Student.id), func.count(Student.class_id))
    ).one()
    return dict(total_classes=total_classes, occupied=occupied,
                empty=total_classes - occupied, total_students=total_students,
                assigned=assigned, unassigned=total_students - assigned)


def get_class_grades(db: Session) -> list[int]:
    return list(db.scalars(select(Class.grade).distinct().order_by(Class.grade)))


def get_class_by_id(db: Session, class_id: int) -> Class:
    class_ = db.get(Class, class_id)
    if class_ is None:
        raise ClassNotFound(status_code=404)
    return class_


def get_classes_students(db: Session, class_id: int, query: ClassStudentListQuery):
    """_Retrieve student items from "students" table._"""
    filters = []
    if query.name is not None:
        filters.append(Student.name.ilike(f"%{query.name}%"))
    if query.nisn is not None:
        filters.append(Student.nisn == query.nisn)

    stmt = (
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
        .where(Student.class_id == class_id, *filters)
        .offset((query.page - 1) * query.limit)
        .limit(query.limit)
        .order_by(Student.nisn.desc())
    )
    students = db.execute(stmt).all()

    results = list(students)

    return results


def post_class(db: Session, class_name: str, grade: int, *, commit: bool = True):
    class_exists = db.scalar(
        select(Class).where(Class.class_name == class_name).where(Class.grade == grade)
    )
    if class_exists:
        raise DuplicateClass

    new_class = Class(class_name=class_name, grade=grade)

    db.add(new_class)
    if commit:
        db.commit()
    else:
        db.flush()

    return new_class


def update_class(db: Session, class_id: int, class_name: str, grade: int, *, commit: bool = True):
    to_update = db.get(Class, class_id)
    if not to_update:
        raise ClassNotFound(status_code=404)

    class_exists = db.scalar(
        select(Class)
        .where(Class.class_name == class_name)
        .where(Class.grade == grade)
        .where(Class.class_id != class_id)
    )
    if class_exists:
        raise DuplicateClass

    to_update.class_name = class_name
    to_update.grade = grade

    if commit:
        db.commit()
    else:
        db.flush()

    return to_update


def delete_class(db: Session, class_id: int):
    to_delete = db.get(Class, class_id)

    if not to_delete:
        raise ClassNotFound(status_code=404)

    db.delete(to_delete)
    db.commit()
