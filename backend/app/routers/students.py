from typing import Annotated

from app.db.session import get_db
from app.models.class_ import Class
from app.models.student import Student
from app.schemas.StudentQuery import StudentQuery
from app.schemas.StudentRequest import StudentRequest
from app.schemas.StudentResponse import StudentResponse
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/students", response_model=list[StudentResponse])
def get_student(query: Annotated[StudentQuery, Query()], db: Session = Depends(get_db)):
    """Retrieve students with optional queries from the database."""
    filters = []

    if query.name is not None:
        filters.append(Student.name.ilike(f"%{query.name}%"))
    if query.class_name is not None:
        filters.append(Class.class_name.ilike(f"%{query.class_name}%"))
    if query.nisn is not None:
        filters.append(Student.nisn == query.nisn)

    stmt = (
        select(
            Student.id, Student.name, Student.nisn, Student.current, Class.class_name, Class.class_id
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


@router.post("/students", response_model=StudentResponse, status_code=201)
def post_student(payload: StudentRequest, db: Session = Depends(get_db)):
    # Check if NISN already exists
    nisn_exist = db.scalar(select(Student).where(Student.nisn == payload.nisn))
    if nisn_exist:
        raise HTTPException(409)

    # Check if class actually exists
    if payload.class_id:
        class_exist = db.get(Class, payload.class_id)
        if not class_exist:
            raise HTTPException(404)

    # Attempt to add student
    new_student = Student(
        name=payload.name,
        nisn=payload.nisn,
        class_id=payload.class_id,
        current=payload.current,
    )

    db.add(new_student)
    db.commit()

    return new_student


@router.put("/students/{student_id}", response_model=StudentResponse)
def put_student(
    student_id: int, payload: StudentRequest, db: Session = Depends(get_db)
):
    # Student to update must exist in the database
    to_update = db.get(Student, student_id)
    if not to_update:
        raise HTTPException(404)

    if payload.class_id:
        class_exist = db.get(Class, payload.class_id)
        if not class_exist:
            raise HTTPException(404)

    # TODO: Prevent duplicate NISN errors on update
    nisn_dupe_exists = db.scalar(
        select(Student)
        .where(Student.id != student_id)
        .where(Student.nisn == payload.nisn)
    )
    if nisn_dupe_exists:
        raise HTTPException(409)

    to_update.name = payload.name
    to_update.class_id = payload.class_id
    to_update.nisn = payload.nisn
    to_update.current = payload.current

    db.commit()

    return to_update


@router.delete("/students/{student_id}", status_code=204)
def delete_scan(student_id: int, db: Session = Depends(get_db)):
    to_delete = db.get(Student, student_id)

    if not to_delete:
        raise HTTPException(404)

    db.delete(to_delete)
    db.commit()
