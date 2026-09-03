from app.models.class_ import Class
from app.models.student import Student
from app.schemas.StudentQuery import StudentQuery
from sqlalchemy import Row, select
from sqlalchemy.orm import Session

from .exceptions import ClassNotFound, DuplicateNisn, StudentNotFound


def get_student(
    db: Session, query: StudentQuery
) -> list[Row[tuple[int, str, str, bool, str, int]]]:
    """_Retrieve a single student items from "students" table._"""
    filters = []

    if query.name is not None:
        filters.append(Student.name.ilike(f"%{query.name}%"))
    if query.class_name is not None:
        filters.append(Class.class_name.ilike(f"%{query.class_name}%"))
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
        .where(*filters)
        .offset((query.page - 1) * query.limit)
        .limit(query.limit)
        .order_by(Student.nisn.desc())
    )
    students = db.execute(stmt).all()

    results = list(students)

    return results


def post_student(
    db: Session, nisn: str, name: str, class_id: int | None, current: bool
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
    )

    db.add(new_student)
    db.commit()

    return new_student


def edit_student(
    db: Session, student_id: int, nisn: str, name: str, class_id: int, current: bool
) -> Student:
    """_Edit one student_

    Raises:
        StudentNotFound
        ClassNotFound
        DuplicateNisn

    Returns:
        Student: _Student model from the database_
    """
    to_update = db.get(Student, student_id)
    if not to_update:
        raise StudentNotFound

    if class_id:
        class_exist = db.get(Class, class_id)
        if not class_exist:
            raise ClassNotFound

    nisn_dupe_exists = db.scalar(
        select(Student).where(Student.id != student_id).where(Student.nisn == nisn)
    )
    if nisn_dupe_exists:
        raise DuplicateNisn

    to_update.name = name
    to_update.class_id = class_id
    to_update.nisn = nisn
    to_update.current = current

    db.commit()

    return to_update

def delete_student(db: Session, student_id: int):
    """_Delete a single student_

    Raises:
        StudentNotFound
    """
    to_delete = db.get(Student, student_id)

    if not to_delete:
        raise StudentNotFound

    db.delete(to_delete)
    db.commit()
