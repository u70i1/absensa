from typing import Annotated

from app.db.session import get_db
from app.models.student import Student
from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.StudentQuery import StudentQuery
from schemas.StudentRequest import StudentRequest
from schemas.StudentResponse import StudentResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/students", response_model=list[StudentResponse])
def get_student(query: Annotated[StudentQuery, Query()], db: Session = Depends(get_db)):
    """Retrieve students with optional queries from the database."""
    filters = []

    if query.name is not None:
        filters.append(Student.name.ilike(f"%{query.name}%"))
    if query.class_ is not None:
        filters.append(Student.class_.ilike(f"%{query.class_}%"))
    if query.nisn is not None:
        filters.append(Student.nisn == query.nisn)

    stmt = (
        select(Student)
        .where(*filters)
        .offset((query.page - 1) * query.limit)
        .limit(query.limit)
    )
    students = db.scalars(stmt).all()

    results = list(students)

    return results


@router.post("/students", response_model=StudentResponse, status_code=201)
def post_student(payload: StudentRequest, db: Session = Depends(get_db)):
    # Check if NISN already exists
    exist = db.scalar(select(Student).where(Student.nisn == payload.nisn))
    if exist:
        raise HTTPException(409)

    # Attempt to add student
    new_student = Student(
        name=payload.name,
        nisn=payload.nisn,
        class_=payload.class_,
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

    # TODO: Prevent duplicate NISN errors on update
    nisn_dupe_exists = db.scalar(
        select(Student)
        .where(Student.id != student_id)
        .where(Student.nisn == payload.nisn)
    )
    if nisn_dupe_exists:
        raise HTTPException(409)

    to_update.name = payload.name
    to_update.class_ = payload.class_
    to_update.current = payload.current
    to_update.nisn = payload.nisn

    db.commit()

    return to_update



@router.delete("/students/{student_id}", status_code=204)
def delete_scan(student_id: int, db: Session = Depends(get_db)):
    to_delete = db.get(Student, student_id)

    if not to_delete:
        raise HTTPException(404)

    db.delete(to_delete)
    db.commit()
