from app.models.class_ import Class
from app.services.exceptions import ClassNotFound, DuplicateClass
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_classes(db: Session, class_name: str, limit: int, page: int):
    filters = []

    if class_name is not None:
        filters.append(Class.class_name.ilike(f"%{class_name}%"))

    classes = db.scalars(
        select(Class)
        .where(*filters)
        .offset((page - 1) * limit)
        .limit(limit)
        .order_by(Class.class_id.desc())
    ).all()

    results = list(classes)

    return results


def post_class(db: Session, class_name: str):
    class_exists = db.scalar(select(Class).where(Class.class_name == class_name))
    if class_exists:
        raise DuplicateClass

    new_class = Class(class_name=class_name)

    db.add(new_class)
    db.commit()

    return new_class


def update_class(db: Session, class_id: int, class_name: str):
    to_update = db.get(Class, class_id)
    if not to_update:
        raise ClassNotFound(status_code=404)

    class_exists = db.scalar(
        select(Class)
        .where(Class.class_name == class_name)
        .where(Class.class_id != class_id)
    )
    if class_exists:
        raise DuplicateClass

    to_update.class_name = class_name

    db.commit()

    return to_update


def delete_class(db: Session, class_id: int):
    to_delete = db.get(Class, class_id)

    if not to_delete:
        raise ClassNotFound(status_code=404)

    db.delete(to_delete)
    db.commit()
