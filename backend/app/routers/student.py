from app.db.session import get_db
from app.models.student import Student
from fastapi import APIRouter, Depends
from schemas.StudentResponse import StudentResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/student", response_model=list[StudentResponse])
def get_student(db: Session = Depends(get_db)):
    # TODO: Add query filters.
    stmt = select(Student)
    students = db.scalars(stmt).all()

    results = list(students)

    return results
