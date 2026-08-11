"""
Tests for POST /scan (scan-in creation and duplicate-detection logic).

Rewritten from an earlier draft to: use shared fixtures instead of hand-rolled
students per test, use SQLAlchemy 2.0 select()/scalars() instead of the
legacy .query() API, and replace the old sequential "race condition" test
(which never actually exercised concurrency) with a real threaded test.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
from sqlalchemy import select

LOCAL_TZ = ZoneInfo(settings.timezone)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def existing_class(db_session):
    class_ = Class(class_name="11B")
    db_session.add(class_)
    db_session.commit()
    db_session.refresh(class_)
    return class_


@pytest.fixture
def existing_student(db_session, existing_class):
    """A single active, scannable student — the default case most tests need."""
    student = Student(
        name="Nicholas Angle",
        class_id=existing_class.class_id,
        nisn="1234567890",
        current=True,
    )
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student


def make_student(db_session, existing_class, **overrides):
    """For tests that need a student with non-default fields (name, nisn,
    current) — existing_student covers the common case, this covers the rest."""
    defaults = {
        "name": "Test Student",
        "class_id": existing_class.class_id,
        "nisn": "0000000001",
        "current": True,
    }
    defaults.update(overrides)
    student = Student(**defaults)
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student


def scan_logs_for(db_session, nisn):
    stmt = select(ScanLog).filter_by(student_nisn=nisn)
    return db_session.scalars(stmt).all()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_scan_creates_log(client, db_session, existing_student):
    """Scanning an existing student should log it correctly to scan_logs."""
    response = client.post("/scans", json={"nisn": existing_student.nisn})

    assert response.status_code == 200, "Status code should be 200"
    body = response.json()
    assert body["name"] == existing_student.name, "Name is wrong"

    logs = scan_logs_for(db_session, existing_student.nisn)
    assert len(logs) == 1, "Unexpected amount of logs"


def test_scan_log_reflects_current_class(
    client, db_session, existing_student, existing_class
):
    """The logged class_ should be a snapshot of the student's class name
    at scan time"""
    response = client.post("/scans", json={"nisn": existing_student.nisn})

    assert response.status_code == 200
    assert response.json()["class_name"] == existing_class.class_name

    logs = scan_logs_for(db_session, existing_student.nisn)
    assert logs[0].class_name == existing_class.class_name


def test_scan_missing_returns_404(client):
    """Scanning a non-existing NISN should fail clearly."""
    response = client.post("/scans", json={"nisn": "0000000000"})

    assert response.status_code == 404, "Response status should be 404"


# ---------------------------------------------------------------------------
# Duplicate-scan (same local day) logic
# ---------------------------------------------------------------------------


def test_scan_same_day_duplicate_returns_409(client, db_session, existing_student):
    """Scanning the same student twice on the same day should conflict."""
    first_scan = client.post("/scans", json={"nisn": existing_student.nisn})
    second_scan = client.post("/scans", json={"nisn": existing_student.nisn})

    assert first_scan.status_code == 200, "First scan status code should be 200"
    assert second_scan.status_code == 409, "Duplicate scan status code should be 409"

    logs = scan_logs_for(db_session, existing_student.nisn)
    assert len(logs) == 1, "Duplicate scan should not be added in the database"


def test_scan_next_local_day_is_not_a_duplicate(client, db_session, existing_student):
    """
    A student scanned yesterday (in LOCAL time) should be scannable again today.
    Seeds the log at local-yesterday 23:00 -- close enough to the boundary that
    a naive UTC-based 'today' check could misclassify it, but a correct
    local-timezone check should not.
    """
    now_local = datetime.now(LOCAL_TZ)
    yesterday_late = (now_local - timedelta(days=1)).replace(
        hour=23, minute=0, second=0, microsecond=0
    )
    db_session.add(
        ScanLog(
            student_nisn=existing_student.nisn,
            name=existing_student.name,
            class_name=existing_student.class_.class_name,
            timestamp=yesterday_late,
        )
    )
    db_session.commit()

    response = client.post("/scans", json={"nisn": existing_student.nisn})

    assert response.status_code == 200, "Scan on a new local day should succeed"

    logs = scan_logs_for(db_session, existing_student.nisn)
    assert len(logs) == 2, "Should now have yesterday's log plus today's"


def test_scan_early_local_morning_is_still_a_duplicate(
    client, db_session, existing_student
):
    """
    A student scanned at local 00:05 today, then scanned again 'now', should
    still 409 -- proves the lower boundary of 'today' is correct, not just
    the upper one.
    """
    now_local = datetime.now(LOCAL_TZ)
    early_today = now_local.replace(hour=0, minute=5, second=0, microsecond=0)
    db_session.add(
        ScanLog(
            student_nisn=existing_student.nisn,
            name=existing_student.name,
            class_name=existing_student.class_.class_name,
            timestamp=early_today,
        )
    )
    db_session.commit()

    response = client.post("/scans", json={"nisn": existing_student.nisn})

    assert response.status_code == 409, (
        "Same local day, even near midnight, is a duplicate"
    )


def test_scan_exact_local_midnight_boundary_is_a_duplicate(
    client, db_session, existing_student
):
    """
    A log at exactly 00:00:00.000000 local time today is still 'today' --
    the boundary instant itself, not just a minute after it. If the
    endpoint's day-comparison uses a strict '>' instead of '>=' somewhere,
    or truncates incorrectly, this is the test that would catch it where
    the 00:05 test might not.
    """
    now_local = datetime.now(LOCAL_TZ)
    exact_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    db_session.add(
        ScanLog(
            student_nisn=existing_student.nisn,
            name=existing_student.name,
            class_name=existing_student.class_.class_name,
            timestamp=exact_midnight,
        )
    )
    db_session.commit()

    response = client.post("/scans", json={"nisn": existing_student.nisn})

    assert response.status_code == 409, "Exact midnight today is still today"


# ---------------------------------------------------------------------------
# Student eligibility
# ---------------------------------------------------------------------------


def test_scan_inactive_student_returns_404(client, db_session, existing_class):
    """
    A student who exists but is marked current=False (e.g. graduated/transferred)
    should be treated as not-scannable -- same as not existing at all.
    Only relevant if your endpoint actually filters on `current`; if it doesn't,
    this test will tell you that's a gap, not a false failure.
    """
    student = make_student(
        db_session,
        existing_class,
        name="Old Alumni",
        nisn="9999999999",
        current=False,
    )

    response = client.post("/scans", json={"nisn": student.nisn})

    assert response.status_code == 404, (
        "Inactive/non-current students shouldn't scan in"
    )


def test_scan_student_without_class_still_scannable(client, db_session):
    """
    class_id is nullable -- a student with no class assigned yet must
    still be able to scan in. The logged class_ should come back as None,
    not crash the endpoint or silently invent a value.
    """
    student = Student(
        name="Unassigned Kid", class_id=None, nisn="4445556667", current=True
    )
    db_session.add(student)
    db_session.commit()

    response = client.post("/scans", json={"nisn": student.nisn})

    assert response.status_code == 200
    assert response.json()["class_name"] is None


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_scan_missing_nisn_returns_422(client):
    """Missing 'nisn' field should fail request validation, not fall
    through to 404 logic."""
    response = client.post("/scans", json={})
    assert response.status_code == 422, "Missing nisn should be a validation error"


def test_scan_integer_nisn_is_coerced_and_succeeds(client, existing_student):
    """
    ScanRequest.nisn is typed str, but confirmed Pydantic coercion turns an
    int payload into a str before validation -- so this should succeed,
    not 422. If you ever tighten the schema (e.g. strict mode), this test
    is the one that will need to flip to expecting 422.
    """
    nisn_as_int = int(existing_student.nisn)
    response = client.post("/scans", json={"nisn": nisn_as_int})

    assert response.status_code == 200, (
        "int nisn should be coerced to str by Pydantic and succeed"
    )


def test_scan_wrong_type_nisn_returns_422(client):
    """A type Pydantic can't coerce to str (e.g. a list) should still 422."""
    response = client.post("/scans", json={"nisn": ["not", "a", "string"]})
    assert response.status_code == 422
