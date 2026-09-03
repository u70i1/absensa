from typing import Annotated

from app.db.session import get_db
from app.schemas.StudentQuery import StudentQuery
from app.schemas.StudentRequest import StudentRequest
from app.schemas.StudentResponse import StudentResponse
from app.services import student_service
from app.services.exceptions import ClassNotFound, DuplicateNisn, StudentNotFound
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/students", response_model=list[StudentResponse])
def get_student(query: Annotated[StudentQuery, Query()], db: Session = Depends(get_db)):
    return student_service.get_student(db, query)


@router.post(
    "/students",
    response_model=StudentResponse,
    status_code=201,
    responses={422: {"description": "Invalid `class_id`"}},
)
def post_student(payload: StudentRequest, db: Session = Depends(get_db)):
    """Create a student item into "students" table"""
    try:
        return student_service.post_student(db, **payload.model_dump())
    except DuplicateNisn:
        raise HTTPException(409, detail="duplicate_nisn")
    except ClassNotFound:
        raise HTTPException(422, detail="class_not_found")


@router.put(
    "/students/{student_id}",
    response_model=StudentResponse,
    responses={
        422: {"description": "Invalid `student_id` or `class_id`"},
        409: {"description": "Conflict in NISN"},
    },
)
def put_student(
    student_id: int, payload: StudentRequest, db: Session = Depends(get_db)
):
    try:
        return student_service.edit_student(db, student_id, **payload.model_dump())
    except StudentNotFound as e:
        raise HTTPException(detail=e.detail, status_code=e.status_code)
    except ClassNotFound as e:
        raise HTTPException(detail=e.detail, status_code=e.status_code)
    except DuplicateNisn as e:
        raise HTTPException(detail=e.detail, status_code=e.status_code)


@router.delete(
    "/students/{student_id}",
    status_code=204,
    responses={422: {"description": "Student is not found"}},
)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    try:
        return student_service.delete_student(db, student_id)
    except StudentNotFound as e:
        raise HTTPException(detail=e.detail, status_code=e.status_code)
