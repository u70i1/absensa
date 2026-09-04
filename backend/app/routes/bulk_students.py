from app.db.session import get_db
from app.schemas.BulkStudentRequest import (
    BulkStudentIdOnly,
    BulkStudentRequest,
    BulkStudentRequestWithId,
)
from app.schemas.BulkStudentResponse import BulkStudentResponse
from app.services import student_bulk_service
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

router = APIRouter()


@router.post(
    "/students/bulk",
    response_model=BulkStudentResponse,
    responses={422: {"description": "All items failed"}},
)
def post_students_bulk(
    payload: list[BulkStudentRequest],
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """Create one or more students in one request."""
    result = student_bulk_service.create_students_bulk(db, payload, dry_run)
    if result["failed"] and not result["succeeded"]:
        return JSONResponse(status_code=422, content=jsonable_encoder(result))
    return result


@router.put("/students/bulk", response_model=BulkStudentResponse)
def update_students_bulk(
    payload: list[BulkStudentRequestWithId],
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """Update multiple students in a single request."""
    result = student_bulk_service.update_students_bulk(db, payload, dry_run)
    if result["failed"] and not result["succeeded"]:
        return JSONResponse(status_code=422, content=jsonable_encoder(result))
    return result


@router.post("/students/bulk-delete", status_code=204)
def delete_students_bulk(
    payload: BulkStudentIdOnly, dry_run: bool = False, db: Session = Depends(get_db)
):
    missing_ids = student_bulk_service.delete_students_bulk(db, payload, dry_run)
    if missing_ids:
        return JSONResponse(
            status_code=422, content=jsonable_encoder({"missing_ids": missing_ids})
        )
