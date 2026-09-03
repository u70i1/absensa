from typing import Annotated

from app.db.session import get_db
from app.schemas.ScanQuery import ScanQuery
from app.schemas.ScanRequest import ScanRequest
from app.schemas.ScanResponse import ScanResponse
from app.services import scan_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.post(
    "/scans",
    response_model=ScanResponse,
    responses={
        422: {"description": "Student's NISN is not found"},
        409: {"description": "Student is already scanned today"},
    },
)
def post_scan(payload: ScanRequest, db: Session = Depends(get_db)):
    """Create a scan item"""
    return scan_service.post_scan(db, payload.nisn)


@router.get(
    "/scans",
    response_model=list[ScanResponse],
)
def get_scan(query: Annotated[ScanQuery, Query()], db: Session = Depends(get_db)):
    """Get items from "scan_logs" table"""
    return scan_service.get_scan(db, **query.model_dump())


@router.get(
    "/scans/{scan_id}",
    response_model=ScanResponse,
    responses={404: {"description": "Student with that id is not found"}},
)
def get_scan_by_id(scan_id: int, db: Session = Depends(get_db)):
    return scan_service.get_scan_by_id(db, scan_id)


@router.delete(
    "/scans/{scan_id}",
    status_code=204,
    responses={404: {"description": "Scan items are not found"}},
)
def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    return scan_service.delete_scan(db, scan_id)
