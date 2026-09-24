from typing import Annotated

from app.core.admin_auth import require_admin
from app.db.session import get_db
from app.schemas.student import StudentListQuery, StudentResponse, StudentWriteRequest
from app.services import student_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/students", response_model=list[StudentResponse])
def get_student(
    query: Annotated[StudentListQuery, Query()], db: Session = Depends(get_db)
):
    return student_service.get_student(db, query)


@router.post(
    "/students",
    response_model=StudentResponse,
    status_code=201,
    responses={422: {"description": "Invalid `class_id`"}},
)
def post_student(payload: StudentWriteRequest, db: Session = Depends(get_db)):
    """Create a student item into "students" table"""
    return student_service.post_student(db, **payload.model_dump())


@router.put(
    "/students/{student_id}",
    response_model=StudentResponse,
    responses={
        422: {"description": "Invalid `student_id` or `class_id`"},
        409: {"description": "Conflict in NISN"},
    },
)
def put_student(
    student_id: int, payload: StudentWriteRequest, db: Session = Depends(get_db)
):
    return student_service.edit_student(db, student_id, **payload.model_dump())


@router.delete(
    "/students/{student_id}",
    status_code=204,
    responses={422: {"description": "Student is not found"}},
)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    return student_service.delete_student(db, student_id)
