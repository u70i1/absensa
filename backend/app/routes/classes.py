from typing import Annotated

from app.db.session import get_db
from app.schemas.ClassQuery import ClassQuery
from app.schemas.ClassRequest import ClassRequest
from app.schemas.ClassResponse import ClassResponse
from app.schemas.StudentQuery import StudentClassQuery
from app.schemas.StudentResponse import StudentResponse
from app.services import class_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/classes", response_model=list[ClassResponse])
def get_classes(query: Annotated[ClassQuery, Query()], db: Session = Depends(get_db)):
    """Retrieve classes; support filter queries"""
    return class_service.get_classes(db, **query.model_dump())


@router.get("/classes/{class_id}/students", response_model=list[StudentResponse])
def get_classes_students(
    class_id: int, query: Annotated[StudentClassQuery, Query()], db: Session = Depends(get_db)
):
    return class_service.get_classes_students(db, class_id, query)


@router.post("/classes", status_code=201, response_model=ClassResponse)
def post_class(payload: ClassRequest, db: Session = Depends(get_db)):
    """Create new Class item in the database"""
    return class_service.post_class(db, payload.class_name)


@router.put("/classes/{class_id}", response_model=ClassResponse)
def update_class(class_id: int, payload: ClassRequest, db: Session = Depends(get_db)):
    """Update the class_name of an existing class item from "classes" table"""
    return class_service.update_class(db, class_id, payload.class_name)


@router.delete("/classes/{class_id}", status_code=204)
def delete_class(class_id: int, db: Session = Depends(get_db)):
    """Delete a class item from "classes" table; deleting a class sets every related student's `class_id` to NULL"""
    return class_service.delete_class(db, class_id)
