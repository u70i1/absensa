from typing import Annotated

from app.db.session import get_db
from app.models.student import Student
from fastapi import APIRouter, Depends, Query
from schemas import StudentQuery
from schemas.StudentResponse import StudentResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/students", response_model=list[StudentResponse])
def get_student(
    filter_query: Annotated[StudentQuery, Query()], db: Session = Depends(get_db)
):
    """Retrieve students with optional queries from the database."""
    filters = []

    if filter_query.name is not None:
        filters.append(Student.name.ilike(f"%{filter_query.name}%"))
    if filter_query.class_ is not None:
        filters.append(Student.class_.ilike(f"%{filter_query.class_}%"))
    if filter_query.nisn is not None:
        filters.append(Student.nisn == filter_query.nisn)

    stmt = (
        select(Student)
        .where(*filters)
        .offset((filter_query.page - 1) * filter_query.limit)
        .limit(filter_query.limit)
    )
    students = db.scalars(stmt).all()

    results = list(students)

    return results
