from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student

# match whatever your app reads from the TZ env var — don't hardcode
# a different literal here than what your app actually uses
LOCAL_TZ = ZoneInfo(settings.timezone)


def make_student_and_class(
    db_session, nisn="1234567890", name="Nicholas Angle", class_name="11B"
):
    """Helper: insert a class + a student linked to it, return the student."""
    class_ = Class(class_name=class_name)
    db_session.add(class_)
    db_session.flush()

    student = Student(name=name, class_id=class_.class_id, nisn=nisn, current=True)
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student


def make_scan(db_session, student, when: datetime):
    """
    Helper: insert a scan log with an EXPLICIT timestamp.

    We can't rely on server_default=func.now() for range-filter tests —
    we need full control over "when" each row happened, otherwise there's
    no way to assert the boundary behavior deterministically.

    ScanLog.class_ is a denormalized string snapshot (not a FK) — we read
    student.class_.class_name at scan-creation time on purpose, so the log
    keeps its historical value even if the student's class later changes
    or the Class row gets deleted (which SET NULLs student.class_id but
    must not rewrite past scan logs).
    """
    class_name = student.class_.class_name if student.class_ is not None else None

    log = ScanLog(
        student_nisn=student.nisn,
        name=student.name,
        class_name=class_name,
        timestamp=when,
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log

def test_delete_scan_removes_row(client, db_session):
    """Deleting an existing scan should actually remove it from the DB —
    not just return a nice status code."""
    student = make_student_and_class(db_session)
    target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

    response = client.delete(f"/scans/{target.scan_id}")

    assert response.status_code == 204, "Successful delete should be 204"
    assert response.content == b"", "204 response should have an empty body"

    # the real assertion: is it actually gone from the DB, not just "did
    # the endpoint say 204". Query directly rather than trusting the response.
    remaining = (
        db_session.query(ScanLog).filter_by(scan_id=target.scan_id).first()
    )
    assert remaining is None, "Scan should no longer exist in the DB"


def test_delete_scan_only_removes_the_targeted_row(client, db_session):
    """Sanity check against an overly broad DELETE (e.g. missing a WHERE
    clause, or filtering on the wrong column) — make sure siblings survive."""
    student = make_student_and_class(db_session)
    target = make_scan(db_session, student, datetime.now(LOCAL_TZ))
    survivor = make_scan(db_session, student, datetime.now(LOCAL_TZ))

    response = client.delete(f"/scans/{target.scan_id}")

    assert response.status_code == 204
    still_there = (
        db_session.query(ScanLog).filter_by(scan_id=survivor.scan_id).first()
    )
    assert still_there is not None, "Unrelated scan should not have been deleted"


def test_delete_scan_missing_returns_404(client, db_session):
    """Deleting a scan_id that doesn't exist should 404, consistent with
    GET /scans/{id}'s behavior for a missing id."""
    # seed something unrelated so a passing test isn't just "table is empty"
    student = make_student_and_class(db_session)
    make_scan(db_session, student, datetime.now(LOCAL_TZ))

    response = client.delete("/scans/999999")

    assert response.status_code == 404


def test_delete_scan_non_integer_id_is_422(client):
    """scan_id typed as int on the path should reject non-numeric input
    at the validation layer, before route logic runs."""
    response = client.delete("/scans/not-an-id")

    assert response.status_code == 422


def test_delete_scan_is_idempotent_failure_on_second_call(client, db_session):
    """Deleting the same id twice: first call succeeds, second call 404s —
    it shouldn't silently 204 again on an already-gone row."""
    student = make_student_and_class(db_session)
    target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

    first = client.delete(f"/scans/{target.scan_id}")
    second = client.delete(f"/scans/{target.scan_id}")

    assert first.status_code == 204
    assert second.status_code == 404
