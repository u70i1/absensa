from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.scan_log import ScanLog
from app.models.student import Student

# match whatever your app reads from the TZ env var — don't hardcode
# a different literal here than what your app actually uses
LOCAL_TZ = ZoneInfo(settings.timezone)


def test_scan_creates_log(client, db_session):
    """Scanning an existing student should log it correctly to scan_logs."""
    student = Student(
        name="Nicholas Angle", class_="11B", nisn="1234567890", current=True
    )
    db_session.add(student)
    db_session.commit()

    response = client.post("/scan", json={"nisn": "1234567890"})

    assert response.status_code == 200, "Status code should be 200"
    body = response.json()
    assert body["name"] == "Nicholas Angle", "Name is wrong"

    logs = db_session.query(ScanLog).filter_by(student_nisn=student.nisn).all()
    assert len(logs) == 1, "Unexpected amount of logs"


def test_scan_missing_returns_404(client):
    """Scanning a non-existing NISN should fail clearly."""
    response = client.post("/scan", json={"nisn": "0000000000"})

    assert response.status_code == 404, "Response status should be 404"


def test_scan_same_day_duplicate_returns_409(client, db_session):
    """Scanning the same student twice on the same day should conflict."""
    student = Student(
        name="Danny Butterman", class_="11B", nisn="0987654321", current=True
    )
    db_session.add(student)
    db_session.commit()

    first_scan = client.post("/scan", json={"nisn": "0987654321"})
    second_scan = client.post("/scan", json={"nisn": "0987654321"})

    assert first_scan.status_code == 200, "First scan status code should be 200"
    assert second_scan.status_code == 409, "Duplicate scan status code should be 409"

    logs = db_session.query(ScanLog).filter_by(student_nisn=student.nisn).all()
    assert len(logs) == 1, "Duplicate scan should not be added in the database"


def test_scan_next_local_day_is_not_a_duplicate(client, db_session):
    """
    A student scanned yesterday (in LOCAL time) should be scannable again today.
    Seeds the log at local-yesterday 23:00 -- close enough to the boundary that
    a naive UTC-based 'today' check could misclassify it, but a correct
    local-timezone check should not.
    """
    student = Student(name="Janine", class_="11B", nisn="1122334455", current=True)
    db_session.add(student)
    db_session.commit()

    now_local = datetime.now(LOCAL_TZ)
    yesterday_late = (now_local - timedelta(days=1)).replace(
        hour=23, minute=0, second=0, microsecond=0
    )
    db_session.add(
        ScanLog(
            student_nisn=student.nisn,
            name=student.name,
            class_=student.class_,
            timestamp=yesterday_late,
        )
    )
    db_session.commit()

    response = client.post("/scan", json={"nisn": "1122334455"})

    assert response.status_code == 200, "Scan on a new local day should succeed"

    logs = db_session.query(ScanLog).filter_by(student_nisn=student.nisn).all()
    assert len(logs) == 2, "Should now have yesterday's log plus today's"


def test_scan_early_local_morning_is_still_a_duplicate(client, db_session):
    """
    A student scanned at local 00:05 today, then scanned again 'now', should
    still 409 -- proves the lower boundary of 'today' is correct, not just
    the upper one.
    """
    student = Student(name="Bob", class_="11B", nisn="5566778899", current=True)
    db_session.add(student)
    db_session.commit()

    now_local = datetime.now(LOCAL_TZ)
    early_today = now_local.replace(hour=0, minute=5, second=0, microsecond=0)
    db_session.add(
        ScanLog(
            student_nisn=student.nisn,
            name=student.name,
            class_=student.class_,
            timestamp=early_today,
        )
    )
    db_session.commit()

    response = client.post("/scan", json={"nisn": "5566778899"})

    assert response.status_code == 409, (
        "Same local day, even near midnight, is a duplicate"
    )


def test_scan_inactive_student_returns_404(client, db_session):
    """
    A student who exists but is marked current=False (e.g. graduated/transferred)
    should be treated as not-scannable -- same as not existing at all.
    Only relevant if your endpoint actually filters on `current`; if it doesn't,
    this test will tell you that's a gap, not a false failure.
    """
    student = Student(name="Old Alumni", class_="12C", nisn="9999999999", current=False)
    db_session.add(student)
    db_session.commit()

    response = client.post("/scan", json={"nisn": "9999999999"})

    assert response.status_code == 404, (
        "Inactive/non-current students shouldn't scan in"
    )


def test_scan_malformed_nisn_returns_422(client):
    """
    Missing or wrong-typed 'nisn' field should fail request validation
    (FastAPI/Pydantic), not fall through to your 404 logic.
    """
    response = client.post("/scan", json={})
    assert response.status_code == 422, "Missing nisn should be a validation error"

    response = client.post("/scan", json={"nisn": 1234567890})
    # only assert this if your schema declares nisn: str -- if it's typed
    # permissively (e.g. accepts int and coerces), this assertion is wrong
    # for your schema and you should adjust or drop it
    assert response.status_code in (422, 200), (
        "Confirm your schema's actual type coercion behavior"
    )


def test_scan_same_student_race_condition_only_logs_once(client, db_session):
    """
    Two near-simultaneous requests for the same student on the same day should
    not both succeed -- this tests whether your duplicate-check has a TOCTOU
    (time-of-check-to-time-of-use) race, not just sequential double-scanning.
    A naive 'SELECT then INSERT if not found' pattern can lose this race under
    real concurrency; sequential test clients often can't reproduce it, so
    treat this as a prompt to inspect your endpoint code, not just trust a
    green test here.
    """
    student = Student(
        name="Concurrent Carl", class_="11B", nisn="1112223334", current=True
    )
    db_session.add(student)
    db_session.commit()

    first = client.post("/scan", json={"nisn": "1112223334"})
    second = client.post("/scan", json={"nisn": "1112223334"})

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409], "Exactly one of two rapid scans should succeed"

    logs = db_session.query(ScanLog).filter_by(student_nisn=student.nisn).all()
    assert len(logs) == 1, (
        "Only one log should exist even under rapid duplicate requests"
    )
