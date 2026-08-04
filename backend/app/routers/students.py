from typing import Annotated

from app.db.session import get_db
from app.models.student import Student
from fastapi import APIRouter, Depends, Query
from schemas.StudentQuery import StudentQuery
from schemas.StudentResponse import StudentResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/students", response_model=list[StudentResponse])
def get_student(
    query: Annotated[StudentQuery, Query()], db: Session = Depends(get_db)
):
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
