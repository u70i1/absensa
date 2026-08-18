from collections import Counter

from app.db.session import get_db
from app.models.class_ import Class
from app.schemas.BulkClassRequest import (
    BulkClassIdOnly,
    BulkClassRequest,
    BulkClassRequestWithId,
)
from app.schemas.BulkClassResponse import BulkClassResponse
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

router = APIRouter()


@router.post(
    "/classes/bulk",
    response_model=BulkClassResponse,
    responses={
        422: {"description": "All items failed"},
    },
)
def post_class_bulk(payload: list[BulkClassRequest], db: Session = Depends(get_db)):
    """Create one or more classes item in one request."""
    enum_payload = enumerate(payload)
    succeeded = []
    failed = []
    REQUIRED_FIELDS = {"class_name"}

    database_class_names = set(db.scalars(select(Class.class_name)).all())
    class_name_payload_counter = Counter([class_.class_name for class_ in payload])

    new_classes = []
    new_classes_meta = []
    for index, class_ in enum_payload:
        success = True

        # Manually validate fields to prevent HTTP 422 for all items
        provided = {
            field for field, value in class_.model_dump().items() if value is not None
        }
        missing = REQUIRED_FIELDS - provided

        if missing:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": f"missing fields: {', '.join(missing)}",
                    "class": class_,
                }
            )

        if class_.class_name and len(class_.class_name) > 10:
            success = False
            failed.append(
                {"index": index, "error": "class_name is too long", "class": class_}
            )

        if class_.class_name and class_.class_name in database_class_names:
            success = False
            failed.append(
                {"index": index, "error": "duplicate class_name", "class": class_}
            )

        if class_name_payload_counter[class_.class_name] > 1:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": "duplicate class_name in batch",
                    "class": class_,
                }
            )

        if success:
            new_class = Class(class_name=class_.class_name)
            new_classes.append(new_class)
            new_classes_meta.append((index, new_class))

    db.add_all(new_classes)
    db.commit()

    # This ensures consistency between the database and response
    for index, new_class in new_classes_meta:
        db.refresh(new_class)
        succeeded.append({"index": index, "class": new_class})

    response = {
        "succeeded": succeeded,
        "failed": failed,
    }

    if len(succeeded) == 0 and len(failed) >= 1:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(response),
        )

    return response


@router.put(
    "/classes/bulk",
    response_model=BulkClassResponse,
    responses={
        422: {"description": "All items failed"},
    },
)
def put_class_bulk(
    payload: list[BulkClassRequestWithId], db: Session = Depends(get_db)
):
    """Update multiple classes in one request."""
    succeeded = []
    failed = []
    enum_payload = enumerate(payload)
    REQUIRED_FIELDS = {"class_id", "class_name"}

    # Simulates the transaction to avoid false collisions when swapping values
    before_transaction = dict(
        db.execute(select(Class.class_id, Class.class_name)).all()  # type: ignore
    )
    class_names_payload = {class_.class_id: class_.class_name for class_ in payload}
    after_transaction = before_transaction | class_names_payload

    database_class_ids = set(db.scalars(select(Class.class_id)).all())

    class_name_counter_payload = Counter(class_.class_name for class_ in payload)
    class_name_counter_after_transaction = Counter(
        class_name for class_name in after_transaction.values()
    )

    updating_classes = []
    for index, class_ in enum_payload:
        success = True

        # Manually handle missing fields to prevent HTTP 422 for all items
        provided = {
            field for field, value in class_.model_dump().items() if value is not None
        }
        missing = REQUIRED_FIELDS - provided
        if missing:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": f"missing fields: {', '.join(missing)}",
                    "class": class_,
                }
            )

        if class_.class_name and len(class_.class_name) > 10:
            success = False
            failed.append(
                {"index": index, "error": "class_name is too long", "class": class_}
            )

        if class_name_counter_payload[class_.class_name] > 1:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": "duplicate class_name in batch",
                    "class": class_,
                }
            )

        if class_name_counter_after_transaction[class_.class_name] > 1:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": "duplicate class_name",
                    "class": class_,
                }
            )

        if class_.class_id not in database_class_ids:
            success = False
            failed.append(
                {"index": index, "error": "cannot find class_id", "class": class_}
            )

        if success:
            updating_class = {
                "class_id": class_.class_id,
                "class_name": class_.class_name,
            }
            updating_classes.append(updating_class)
            succeeded.append(
                {
                    "index": index,
                    "class": updating_class,
                }
            )

    db.execute(text("SET CONSTRAINTS classes_class_name_key DEFERRED"))
    db.execute(update(Class), updating_classes)
    db.commit()

    response = {
        "succeeded": succeeded,
        "failed": failed,
    }

    if len(succeeded) < 1 and len(failed) >= 1:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(response),
        )

    return response


@router.post(
    "/classes/bulk-delete",
    status_code=204,
    responses={422: {"description": "If at least one item failed"}},
)
def delete_class_bulk(payload: BulkClassIdOnly, db: Session = Depends(get_db)):
    """Delete multiple classes in one request."""
    payload_ids = set(payload.ids)
    if not payload_ids:
        return

    db_ids = set(db.scalars(select(Class.class_id)).all())

    missing_ids = []
    for i in payload_ids:
        if i in db_ids:
            continue
        missing_ids.append(i)
    if len(missing_ids) >= 1:
        return JSONResponse(
            status_code=422, content=jsonable_encoder({"missing_ids": missing_ids})
        )

    db.execute(delete(Class).where(Class.class_id.in_(payload_ids)))
