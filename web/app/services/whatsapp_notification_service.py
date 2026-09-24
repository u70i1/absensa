"""School-wide absence notifications; the bridge only transports final messages."""

import logging
import random
import re
import time as time_module
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings as app_settings
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
from app.models.whatsapp_notification import WhatsAppNotificationLog as Log
from app.models.whatsapp_notification import WhatsAppNotificationSettings as Settings
from app.services.whatsapp_gateway_service import (
    GatewayProblem,
    WhatsAppGateway,
    normalize_phone,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo(app_settings.timezone)
VARIABLE = re.compile(r"{{\s*(nama|kelas)\s*}}")
RUN_LEASE = timedelta(minutes=2)


class NotificationProblem(Exception):
    def __init__(self, detail: str, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def validate_template(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 2000:
        raise NotificationProblem("Templat harus berisi 1–2000 karakter.", 422)
    remainder = VARIABLE.sub("", value)
    if "{{" in remainder or "}}" in remainder or "{%" in value or "{#" in value:
        raise NotificationProblem("Gunakan hanya variabel {{nama}} dan {{kelas}}.", 422)
    return value


def render_message(template: str, name: str, class_name: str | None) -> str:
    validate_template(template)
    return VARIABLE.sub(
        lambda match: name if match.group(1) == "nama" else (class_name or "-"),
        template,
    )


def guardian_recipient(value: str) -> str:
    """Student records permit local Indonesian 08 numbers; the bridge uses 62."""
    digits = value.strip()
    return normalize_phone("62" + digits[1:] if digits.startswith("08") else digits)


def get_settings(db: Session, *, lock: bool = False) -> Settings:
    statement = select(Settings).where(Settings.id == 1)
    if lock:
        statement = statement.with_for_update()
    result = db.scalar(statement)
    if result is None:
        raise RuntimeError(
            "WhatsApp notification settings migration has not been applied"
        )
    return result


def update_settings(
    db: Session,
    *,
    send_time: time,
    minimum_attendance: int,
    message_template: str,
    safe_mode: bool,
) -> Settings:
    if minimum_attendance < 0:
        raise NotificationProblem("Minimum kehadiran tidak boleh negatif.", 422)
    template = validate_template(message_template)
    config = get_settings(db, lock=True)
    config.send_time = send_time
    config.minimum_attendance = minimum_attendance
    config.message_template = template
    config.safe_mode = safe_mode
    db.commit()
    return config


def set_enabled(db: Session, enabled: bool) -> None:
    config = get_settings(db, lock=True)
    config.enabled = enabled
    db.commit()


def _last_skip(db: Session, day):
    return (
        db.scalar(
            select(Log.kind)
            .where(Log.day == day, Log.kind.in_(("skip", "cancel_skip")))
            .order_by(Log.id.desc())
            .limit(1)
        )
        == "skip"
    )


def daily_state(db: Session, at: datetime | None = None) -> dict:
    at = at or now_local()
    day = at.astimezone(LOCAL_TZ).date()
    run = db.scalar(select(Log).where(Log.day == day, Log.kind == "run"))
    skipped = _last_skip(db, day)
    expired = run and run.lease_until and run.lease_until <= datetime.now(timezone.utc)
    if run and run.status == "completed":
        state = "completed"
    elif run and (run.status == "interrupted" or expired):
        state = "interrupted"
    elif run:
        state = "running"
    elif skipped:
        state = "skipped"
    else:
        state = "ready"
    reasons = {
        "completed": "Layanan sudah berjalan hari ini.",
        "running": "Pengiriman sedang berlangsung.",
        "skipped": "Hari ini telah dilewati.",
        "interrupted": "Pengiriman terhenti; lanjutkan untuk mengirim hanya kepada siswa yang belum dicoba.",
    }
    return {
        "date": day.isoformat(),
        "state": state,
        "can_send_now": state in ("ready", "interrupted"),
        "can_skip": state == "ready",
        "can_cancel_skip": state == "skipped",
        "reason": reasons.get(state),
    }


def skip_today(
    db: Session, *, cancel: bool = False, at: datetime | None = None
) -> dict:
    at = at or now_local()
    get_settings(db, lock=True)
    state = daily_state(db, at)
    expected = "skipped" if cancel else "ready"
    if state["state"] != expected:
        db.rollback()
        raise NotificationProblem(state["reason"] or "Status hari ini telah berubah.")
    db.add(
        Log(
            day=at.astimezone(LOCAL_TZ).date(),
            kind="cancel_skip" if cancel else "skip",
            status="applied",
        )
    )
    db.commit()
    return daily_state(db, at)


def _day_bounds(at: datetime):
    start = at.astimezone(LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _attendance_count(db: Session, at: datetime) -> int:
    start, end = _day_bounds(at)
    return (
        db.scalar(
            select(func.count(func.distinct(ScanLog.student_id)))
            .join(Student, Student.id == ScanLog.student_id)
            .where(
                Student.current.is_(True),
                ScanLog.timestamp >= start,
                ScanLog.timestamp < end,
            )
        )
        or 0
    )


def _absent_students(db: Session, at: datetime):
    start, end = _day_bounds(at)
    present = (
        select(ScanLog.scan_id)
        .where(
            ScanLog.student_id == Student.id,
            ScanLog.timestamp >= start,
            ScanLog.timestamp < end,
        )
        .exists()
    )
    return db.execute(
        select(Student.id, Student.name, Student.guardian_phone, Class.class_name)
        .outerjoin(Class, Class.class_id == Student.class_id)
        .where(Student.current.is_(True), ~present)
        .order_by(Student.id)
    ).all()


def _claim(db: Session, day, student_id: int) -> Log | None:
    result = db.execute(
        insert(Log)
        .values(day=day, kind="delivery", status="claimed", student_id=student_id)
        .on_conflict_do_nothing()
        .returning(Log.id)
    ).scalar_one_or_none()
    db.commit()
    return db.get(Log, result) if result else None


def _renew_run(db: Session, run_id: int, at: datetime) -> None:
    run = db.get(Log, run_id)
    run.lease_until = at.astimezone(timezone.utc) + RUN_LEASE
    db.commit()


def run_daily(
    db: Session,
    gateway: WhatsAppGateway,
    *,
    manual: bool = False,
    at: datetime | None = None,
    sleep=time_module.sleep,
    prepare_only: bool = False,
    reserved_run_id: int | None = None,
) -> dict:
    at = at or now_local()
    local = at.astimezone(LOCAL_TZ)
    day = local.date()
    config = get_settings(db, lock=True)
    if not manual:
        if not config.enabled:
            db.rollback()
            return {"state": "disabled"}
        if local.time().replace(tzinfo=None) < config.send_time:
            db.rollback()
            return {"state": "before_time"}
        if _attendance_count(db, at) < config.minimum_attendance:
            db.rollback()
            return {"state": "below_minimum"}
    if _last_skip(db, day):
        db.rollback()
        return {"state": "skipped"}
    run = db.scalar(
        select(Log).where(Log.day == day, Log.kind == "run").with_for_update()
    )
    now_utc = datetime.now(timezone.utc)
    if run and (
        run.status == "completed"
        or (run.lease_until and run.lease_until > now_utc and run.id != reserved_run_id)
    ):
        db.rollback()
        return {"state": "already_run" if run.status == "completed" else "running"}
    if gateway.status().state != "connected":
        db.rollback()
        raise NotificationProblem("WhatsApp belum terhubung.", 503)
    if run is None:
        run = Log(day=day, kind="run", status="running")
        db.add(run)
        db.flush()
    run.status = "queued" if prepare_only else "running"
    run.lease_until = now_utc + RUN_LEASE
    run_id = run.id
    template, safe_mode, delay = (
        config.message_template,
        config.safe_mode,
        config.delay_seconds,
    )
    db.commit()
    if prepare_only:
        return {"state": "queued", "run_id": run_id}

    sent = failed = 0
    attempted = False
    interrupted = False
    for student in _absent_students(db, at):
        if attempted and safe_mode:
            _renew_run(db, run_id, datetime.now(timezone.utc))
            sleep(delay)
        if not manual and not get_settings(db).enabled:
            interrupted = True
            break
        # Recheck just before claiming: a scan may arrive during a safe-mode delay.
        start, end = _day_bounds(at)
        if db.scalar(
            select(ScanLog.scan_id)
            .where(
                ScanLog.student_id == student.id,
                ScanLog.timestamp >= start,
                ScanLog.timestamp < end,
            )
            .limit(1)
        ):
            continue
        if not student.guardian_phone:
            continue
        _renew_run(db, run_id, datetime.now(timezone.utc))
        try:
            phone = guardian_recipient(student.guardian_phone)
            message = render_message(template, student.name, student.class_name)
        except (GatewayProblem, NotificationProblem) as exc:
            log = _claim(db, day, student.id)
            if log:
                log.status = "failed"
                log.detail = "invalid_contact_or_template"
                db.commit()
                failed += 1
            logger.warning(
                "WhatsApp delivery validation failed for student_id=%s: %s",
                student.id,
                exc.detail,
            )
            continue
        log = _claim(db, day, student.id)
        if log is None:
            continue
        attempted = True
        try:
            gateway.send_message(phone, message)
        except GatewayProblem as exc:
            interrupted = exc.status_code == 409 or exc.status_code >= 500
            log.status = "failed"
            log.detail = "gateway_unavailable" if interrupted else "delivery_rejected"
            failed += 1
            logger.warning(
                "WhatsApp delivery failed for student_id=%s: %s", student.id, exc.detail
            )
        else:
            log.status = "sent"
            sent += 1
        db.commit()
        if interrupted:
            break
    run = db.get(Log, run_id)
    run.status = "interrupted" if interrupted else "completed"
    run.lease_until = None
    db.commit()
    logger.info(
        "WhatsApp %s run day=%s status=%s sent=%s failed=%s",
        "manual" if manual else "scheduled",
        day,
        run.status,
        sent,
        failed,
    )
    return {"state": run.status, "sent": sent, "failed": failed}


def send_test(
    db: Session, gateway: WhatsAppGateway, *, at: datetime | None = None
) -> dict:
    at = at or now_local()
    config = get_settings(db)
    students = db.execute(
        select(Student.id, Student.name, Student.guardian_phone, Class.class_name)
        .outerjoin(Class, Class.class_id == Student.class_id)
        .where(Student.guardian_phone.is_not(None), Student.guardian_phone != "")
    ).all()
    eligible = []
    for student in students:
        try:
            eligible.append((student, guardian_recipient(student.guardian_phone)))
        except GatewayProblem:
            continue
    if not eligible:
        raise NotificationProblem(
            "Belum ada siswa dengan nomor wali yang dapat digunakan.", 422
        )
    student, phone = random.choice(eligible)
    message = render_message(config.message_template, student.name, student.class_name)
    log = Log(
        day=at.astimezone(LOCAL_TZ).date(),
        kind="test",
        status="claimed",
        student_id=student.id,
    )
    db.add(log)
    db.commit()
    try:
        gateway.send_message(phone, message)
    except GatewayProblem as exc:
        log.status = "failed"
        log.detail = "delivery_failed"
        db.commit()
        logger.warning(
            "WhatsApp test failed for student_id=%s: %s", student.id, exc.detail
        )
        raise
    log.status = "sent"
    db.commit()
    logger.info("WhatsApp test sent for student_id=%s", student.id)
    return {"student_id": student.id, "name": student.name}
