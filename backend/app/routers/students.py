from typing import Annotated

from app.db.session import get_db
from app.models.student import Student
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from schemas.StudentResponse import StudentResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


class FilterParams(BaseModel):
    """Query model for GET /student"""

    limit: int = Field(10, ge=1, le=100)
    page: int = Field(1, ge=1)


@router.get("/students", response_model=list[StudentResponse])
def get_student(
    filter_query: Annotated[FilterParams, Query()], db: Session = Depends(get_db)
):
    # TODO: Add query filters.
    stmt = (
        select(Student)
        .offset((filter_query.page - 1) * filter_query.limit)
        .limit(filter_query.limit)
    )
    students = db.scalars(stmt).all()

    results = list(students)

    return results
