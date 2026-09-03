from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.db.session import get_db
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
from app.schemas.ScanQuery import ScanQuery
from app.schemas.ScanRequest import ScanRequest
from app.schemas.ScanResponse import ScanResponse
from app.services import scan_service
from app.services.exceptions import ScanDuplicate, StudentNotFound
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
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
    try:
        return scan_service.post_scan(db, payload.nisn)
    except StudentNotFound as e:
        raise HTTPException(e.status_code, e.detail)
    except ScanDuplicate as e:
            raise HTTPException(e.status_code, e.detail)


@router.get(
    "/scans",
    response_model=list[ScanResponse],
)
def get_scan(query: Annotated[ScanQuery, Query()], db: Session = Depends(get_db)):
    """Get items from "scan_logs" table"""

    filters = []

    if query.nisn is not None:
        filters.append(Student.nisn == query.nisn)

    if query.student_id is not None:
        filters.append(ScanLog.student_id == query.student_id)

    if query.date_from is not None:
        filters.append(
            ScanLog.timestamp >= query.date_from.replace(hour=0, minute=0, second=0)
        )

    if query.date_to is not None:
        filters.append(
            ScanLog.timestamp <= query.date_to.replace(hour=23, minute=59, second=59)
        )

    stmt = (
        select(
            ScanLog.scan_id,
            ScanLog.name,
            ScanLog.class_name,
            Student.class_id,
            ScanLog.student_id,
            Student.nisn,
            ScanLog.timestamp,
        )
        .outerjoin(Student, Student.id == ScanLog.student_id)
        .where(*filters)
        .offset((query.page - 1) * query.limit)
        .limit(query.limit)
        .order_by(ScanLog.timestamp.desc())
    )
    scan_logs = db.execute(stmt).all()

    results = list(scan_logs)

    return results


@router.get(
    "/scans/{scan_id}",
    response_model=ScanResponse,
    responses={404: {"description": "Student with that id is not found"}},
)
def get_scan_by_id(scan_id: int, db: Session = Depends(get_db)):
    stmt = (
        select(
            ScanLog.scan_id,
            ScanLog.name,
            ScanLog.class_name,
            Student.class_id,
            ScanLog.student_id,
            Student.nisn,
            ScanLog.timestamp,
        )
        .outerjoin(Student, Student.id == ScanLog.student_id)
        .where(ScanLog.scan_id == scan_id)
    )
    result = db.execute(stmt).first()
    if not result:
        raise HTTPException(404)

    return result


@router.delete(
    "/scans/{scan_id}",
    status_code=204,
    responses={404: {"description": "Scan items are not found"}},
)
def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    to_delete = db.get(ScanLog, scan_id)

    if not to_delete:
        raise HTTPException(422)

    db.delete(to_delete)
    db.commit()
