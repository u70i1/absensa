from app.db.session import get_db
from app.models.class_ import Class
from app.schemas.ClassRequest import ClassRequest
from app.schemas.ClassResponse import ClassResponse
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/classes", status_code=201, response_model=ClassResponse)
def post_class(payload: ClassRequest, db: Session = Depends(get_db)):
    class_name = payload.class_name

    # Check if class_name already exists
    class_exists = db.scalar(select(Class).where(Class.class_name == class_name))
    if class_exists:
        raise HTTPException(409)

    # Insert class
    new_class = Class(class_name=class_name)

    db.add(new_class)
    db.commit()

    return new_class


@router.put("/classes/{class_id}", response_model=ClassResponse)
def update_class(class_id: int, payload: ClassRequest, db: Session = Depends(get_db)):
    class_name = payload.class_name

    to_update = db.get(Class, class_id)
    if not to_update:
        raise HTTPException(404)

    # Check if class_name already exists
    class_exists = db.scalar(
        select(Class)
        .where(Class.class_name == class_name)
        .where(Class.class_id != class_id)
    )
    if class_exists:
        raise HTTPException(409)

    # update class

    to_update.class_name = payload.class_name

    db.commit()

    return to_update

@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(class_id: int, db: Session = Depends(get_db)):
    to_delete = db.get(Class, class_id)

    if not to_delete:
        raise HTTPException(404)

    db.delete(to_delete)
    db.commit()
