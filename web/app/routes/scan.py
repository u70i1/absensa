from typing import Annotated

from app.core.access_auth import require_operator
from app.core.admin_auth import require_admin
from app.db.session import get_db
from app.schemas.scan import ScanCreateRequest, ScanListQuery, ScanResponse
from app.services import scan_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.post(
    "/scans",
    dependencies=[Depends(require_operator)],
    response_model=ScanResponse,
    responses={
        422: {"description": "Student's NISN is not found"},
        409: {"description": "Student is already scanned today"},
    },
)
def post_scan(payload: ScanCreateRequest, db: Session = Depends(get_db)):
    """Create a scan item"""
    return scan_service.post_scan(db, payload.nisn)


@router.get(
    "/scans",
    dependencies=[Depends(require_operator)],
    response_model=list[ScanResponse],
)
def get_scan(query: Annotated[ScanListQuery, Query()], db: Session = Depends(get_db)):
    """Get items from "scan_logs" table"""
    return scan_service.get_scan(db, **query.model_dump())


@router.get(
    "/scans/{scan_id}",
    dependencies=[Depends(require_admin)],
    response_model=ScanResponse,
    responses={404: {"description": "Student with that id is not found"}},
)
def get_scan_by_id(scan_id: int, db: Session = Depends(get_db)):
    return scan_service.get_scan_by_id(db, scan_id)


@router.delete(
    "/scans/{scan_id}",
    dependencies=[Depends(require_admin)],
    status_code=204,
    responses={404: {"description": "Scan items are not found"}},
)
def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    return scan_service.delete_scan(db, scan_id)
