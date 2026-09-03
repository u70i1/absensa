from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
from app.services.exceptions import DuplicateScanLog, ScanLogNotFound, StudentNotFound
from sqlalchemy import select
from sqlalchemy.orm import Session

tz_info = ZoneInfo(settings.timezone)


def post_scan(db: Session, nisn: str):
    """_Create a scan_log entry_

    Raises:
        DuplicateScanLog
        StudentNotFound
    """
    start_today = datetime.now(tz=tz_info).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_today = datetime.now(tz=tz_info).replace(
        hour=23, minute=59, second=59, microsecond=0
    )

    student_id = db.scalar(select(Student.id).where(Student.nisn == nisn))

    exist = db.scalars(
        select(ScanLog)
        .where(ScanLog.timestamp.between(start_today, end_today))
        .where(ScanLog.student_id == student_id)
    ).first()

    if exist:
        raise DuplicateScanLog()

    scanned_student = db.execute(
        select(
            Student.id, Student.name, Student.class_id, Student.nisn, Class.class_name
        )
        .outerjoin(Class, Class.class_id == Student.class_id)
        .where(Student.current == True)
        .where(Student.id == student_id)
    ).first()

    if scanned_student is None:
        raise StudentNotFound()

    timestamp = datetime.now(tz=tz_info)
    new_scan_log = ScanLog(
        student_id=student_id,
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
        "student_id": scanned_student.id,
        "timestamp": timestamp,
    }


def get_scan(
    db: Session,
    nisn: str,
    student_id: int,
    date_from: datetime,
    date_to: datetime,
    page: int,
    limit: int,
):
    filters = []

    if nisn is not None:
        filters.append(Student.nisn == nisn)

    if student_id is not None:
        filters.append(ScanLog.student_id == student_id)

    if date_from is not None:
        filters.append(
            ScanLog.timestamp >= date_from.replace(hour=0, minute=0, second=0)
        )

    if date_to is not None:
        filters.append(
            ScanLog.timestamp <= date_to.replace(hour=23, minute=59, second=59)
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
        .offset((page - 1) * limit)
        .limit(limit)
        .order_by(ScanLog.timestamp.desc())
    )
    scan_logs = db.execute(stmt).all()

    results = list(scan_logs)

    return results


def get_scan_by_id(db: Session, scan_id: int):
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
        raise ScanLogNotFound(status_code=404)

    return result


def delete_scan(db: Session, scan_id: int):
    to_delete = db.get(ScanLog, scan_id)

    if not to_delete:
        raise ScanLogNotFound

    db.delete(to_delete)
    db.commit()
