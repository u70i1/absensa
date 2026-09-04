from app.db.session import get_db
from app.schemas.BulkClassRequest import (
    BulkClassIdOnly,
    BulkClassRequest,
    BulkClassRequestWithId,
)
from app.schemas.BulkClassResponse import BulkClassResponse
from app.services import class_bulk_service
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

router = APIRouter()


@router.post(
    "/classes/bulk",
    response_model=BulkClassResponse,
    responses={422: {"description": "All items failed"}},
)
def post_class_bulk(
    payload: list[BulkClassRequest],
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """Create one or more classes in one request."""
    result = class_bulk_service.create_classes_bulk(db, payload, dry_run)
    if result["failed"] and not result["succeeded"]:
        return JSONResponse(status_code=422, content=jsonable_encoder(result))
    return result


@router.put(
    "/classes/bulk",
    response_model=BulkClassResponse,
    responses={422: {"description": "All items failed"}},
)
def put_class_bulk(
    payload: list[BulkClassRequestWithId],
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """Update multiple classes in one request."""
    result = class_bulk_service.update_classes_bulk(db, payload, dry_run)
    if result["failed"] and not result["succeeded"]:
        return JSONResponse(status_code=422, content=jsonable_encoder(result))
    return result


@router.post(
    "/classes/bulk-delete",
    status_code=204,
    responses={422: {"description": "If at least one item failed"}},
)
def delete_class_bulk(
    payload: BulkClassIdOnly, dry_run: bool = False, db: Session = Depends(get_db)
):
    """Delete multiple classes in one request."""
    missing_ids = class_bulk_service.delete_classes_bulk(db, payload, dry_run)
    if missing_ids:
        return JSONResponse(
            status_code=422, content=jsonable_encoder({"missing_ids": missing_ids})
        )
