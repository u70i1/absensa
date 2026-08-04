from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.db.session import get_db
from app.models.scan_log import ScanLog
from app.models.student import Student
from fastapi import APIRouter, Depends, HTTPException
from schemas.ScanRequest import ScanRequest
from schemas.ScanResponse import ScanResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

tz_info = ZoneInfo(settings.timezone)

router = APIRouter()


@router.post("/scan", response_model=ScanResponse)
def scan(payload: ScanRequest, db: Session = Depends(get_db)):
    # Check if student is already scanned today
    start_today = datetime.now(tz=tz_info).replace(hour=0, minute=0, second=0)
    end_today = datetime.now(tz=tz_info).replace(hour=23, minute=59, second=59)

    exist = db.scalars(
        select(ScanLog)
        .where(ScanLog.timestamp.between(start_today, end_today))
        .where(ScanLog.student_nisn == payload.nisn)
    ).all()

    if exist:
        raise HTTPException(status_code=409, detail="student is already scanned today")

    # Insert to the database
    scanned_student = db.scalars(
        select(Student)
        .where(Student.current == True)
        .where(Student.nisn == payload.nisn)
    ).first()

    if scanned_student is None:
        raise HTTPException(status_code=404)

    timestamp = datetime.now(tz=tz_info)
    new_scan_log = ScanLog(
        student_nisn=payload.nisn,
        name=scanned_student.name,
        class_=scanned_student.class_,
        timestamp=timestamp,
    )

    db.add(new_scan_log)
    db.commit()

    return {
        "scan_id": new_scan_log.scan_id,
        "timestamp": timestamp,
        "name": scanned_student.name,
        "class_name": scanned_student.class_,
        "nisn": scanned_student.nisn,
    }
