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
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

tz_info = ZoneInfo(settings.timezone)

router = APIRouter()


@router.post("/scan", response_model=ScanResponse)
def post_scan(payload: ScanRequest, db: Session = Depends(get_db)):
    # Check if student is already scanned today
    start_today = datetime.now(tz=tz_info).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_today = datetime.now(tz=tz_info).replace(
        hour=23, minute=59, second=59, microsecond=0
    )

    exist = db.scalars(
        select(ScanLog)
        .where(ScanLog.timestamp.between(start_today, end_today))
        .where(ScanLog.student_nisn == payload.nisn)
    ).first()

    if exist:
        raise HTTPException(status_code=409, detail="student is already scanned today")

    # Insert to the database
    scanned_student = db.execute(
        select(Student.name, Student.class_id, Student.nisn, Class.class_name)
        .outerjoin(Class, Class.class_id == Student.class_id)
        .where(Student.current == True)
        .where(Student.nisn == payload.nisn)
    ).first()

    if scanned_student is None:
        raise HTTPException(status_code=404)

    timestamp = datetime.now(tz=tz_info)
    new_scan_log = ScanLog(
        student_nisn=payload.nisn,
        name=scanned_student.name,
        class_name=scanned_student.class_name,
        timestamp=timestamp,
    )

    db.add(new_scan_log)
    db.commit()

    return {
        "scan_id": new_scan_log.scan_id,
        "name": new_scan_log.name,
        "class_name": new_scan_log.class_name,
        "class_id": scanned_student.class_id,
        "student_nisn": scanned_student.nisn,
        "timestamp": timestamp,
    }


@router.get("/scans", response_model=list[ScanResponse])
def get_scan(query: Annotated[ScanQuery, Query()], db: Session = Depends(get_db)):
    """GET /scans
    Returns:
        list[ScanResponse]
    """

    filters = []

    if query.nisn is not None:
        filters.append(ScanLog.student_nisn == query.nisn)

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
            ScanLog.student_nisn,
            ScanLog.timestamp,
        )
        .join(Student, Student.nisn == ScanLog.student_nisn)
        .where(*filters)
        .offset((query.page - 1) * query.limit)
        .limit(query.limit)
        .order_by(ScanLog.timestamp.desc())
    )
    scan_logs = db.execute(stmt).all()

    results = list(scan_logs)

    return results


@router.get("/scans/{scan_id}", response_model=ScanResponse)
def get_scan_by_id(scan_id: int, db: Session = Depends(get_db)):
    stmt = (
        select(
            ScanLog.scan_id,
            ScanLog.name,
            ScanLog.class_name,
            Student.class_id,
            ScanLog.student_nisn,
            ScanLog.timestamp,
        )
        .join(Student, Student.nisn == ScanLog.student_nisn)
        .where(ScanLog.scan_id == scan_id)
    )
    result = db.execute(stmt).first()
    if not result:
        raise HTTPException(404)

    return result


@router.delete("/scans/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    to_delete = db.get(ScanLog, scan_id)

    if not to_delete:
        raise HTTPException(404)

    db.delete(to_delete)
    db.commit()
