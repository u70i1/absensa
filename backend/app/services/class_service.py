from app.models.class_ import Class
from app.models.student import Student
from app.schemas.StudentQuery import StudentClassQuery
from app.services.exceptions import ClassNotFound, DuplicateClass
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_classes(
    db: Session, class_name: str, limit: int, page: int, grade: int | None = None
):
    filters = []

    if class_name is not None:
        filters.append(Class.class_name.ilike(f"%{class_name}%"))
    if grade is not None:
        filters.append(Class.grade == grade)

    classes = db.scalars(
        select(Class)
        .where(*filters)
        .offset((page - 1) * limit)
        .limit(limit)
        .order_by(Class.class_id.desc())
    ).all()

    results = list(classes)

    return results


def get_classes_students(db: Session, class_id: int, query: StudentClassQuery):
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


def post_class(db: Session, class_name: str, grade: int):
    class_exists = db.scalar(
        select(Class)
        .where(Class.class_name == class_name)
        .where(Class.grade == grade)
    )
    if class_exists:
        raise DuplicateClass

    new_class = Class(class_name=class_name, grade=grade)

    db.add(new_class)
    db.commit()

    return new_class


def update_class(db: Session, class_id: int, class_name: str, grade: int):
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

    db.commit()

    return to_update


def delete_class(db: Session, class_id: int):
    to_delete = db.get(Class, class_id)

    if not to_delete:
        raise ClassNotFound(status_code=404)

    db.delete(to_delete)
    db.commit()
