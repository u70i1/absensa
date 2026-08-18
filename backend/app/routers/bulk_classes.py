from app.db.session import get_db
from app.models.class_ import Class
from app.schemas.BulkClassRequest import BulkClassRequest
from app.schemas.BulkClassResponse import BulkClassResponse
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
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
    """Create one or more classes item in one request"""
    enum_payload = enumerate(payload)
    failed = []
    REQUIRED_FIELDS = {"class_name"}

    existing_class_names = set(db.scalars(select(Class.class_name)).all())

    new_classes = []
    new_classes_meta = []
    for index, class_ in enum_payload:
        success = True

        # Check for missing fields
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

        # Check for duplicate class_name
        if class_.class_name in existing_class_names:
            success = False
            failed.append(
                {"index": index, "error": "duplicate class_name", "class": class_}
            )

        if success:
            new_class = Class(class_name=class_.class_name)
            new_classes.append(new_class)
            new_classes_meta.append((index, new_class))

        db.add_all(new_classes)
        db.commit()

        succeeded = []
        for index, new_class in new_classes_meta:
            db.refresh(new_class)
            succeeded.append({"index": index, "class": new_class})

        response = {
            "succeeded": succeeded,
            "failed": failed,
        }

        if len(new_classes_meta) < 1 and len(failed) >= 1:
            return JSONResponse(
                status_code=422,
                content=jsonable_encoder(response),
            )

        return response


@router.put("/classes/bulk")
def put_class_bulk():
    pass


@router.post("/classes/bulk-delete")
def delete_class_bulk():
    pass
