from typing import Annotated

from app.db.session import get_db
from app.models.class_ import Class
from app.schemas.ClassQuery import ClassQuery
from app.schemas.ClassRequest import ClassRequest
from app.schemas.ClassResponse import ClassResponse
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/classes", response_model=list[ClassResponse])
def get_student(query: Annotated[ClassQuery, Query()], db: Session = Depends(get_db)):
    """Retrieve classes; support filter queries"""
    filters = []

    if query.class_name is not None:
        filters.append(Class.class_name.ilike(f"%{query.class_name}%"))

    classes = db.scalars(
        select(Class)
        .where(*filters)
        .offset((query.page - 1) * query.limit)
        .limit(query.limit)
        .order_by(Class.class_id.desc())
    ).all()

    results = list(classes)

    return results


@router.post("/classes", status_code=201, response_model=ClassResponse)
def post_class(payload: ClassRequest, db: Session = Depends(get_db)):
    """Create new Class item in the database"""
    class_name = payload.class_name

    class_exists = db.scalar(select(Class).where(Class.class_name == class_name))
    if class_exists:
        raise HTTPException(409)

    new_class = Class(class_name=class_name)

    db.add(new_class)
    db.commit()

    return new_class


@router.put("/classes/{class_id}", response_model=ClassResponse)
def update_class(class_id: int, payload: ClassRequest, db: Session = Depends(get_db)):
    """Update the class_name of an existing class item from "classes" table"""
    class_name = payload.class_name

    to_update = db.get(Class, class_id)
    if not to_update:
        raise HTTPException(404)

    class_exists = db.scalar(
        select(Class)
        .where(Class.class_name == class_name)
        .where(Class.class_id != class_id)
    )
    if class_exists:
        raise HTTPException(409)

    to_update.class_name = payload.class_name

    db.commit()

    return to_update


@router.delete("/classes/{class_id}", status_code=204)
def delete_class(class_id: int, db: Session = Depends(get_db)):
    """Delete a class item from "classes" table; deleting a class sets every related student's `class_id` to NULL"""
    to_delete = db.get(Class, class_id)

    if not to_delete:
        raise HTTPException(404)

    db.delete(to_delete)
    db.commit()
