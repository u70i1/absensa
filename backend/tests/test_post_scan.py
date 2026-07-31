from datetime import datetime, timedelta, timezone

from app.models.scan_log import ScanLog
from app.models.student import Student


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

    logs = db_session.query(ScanLog).filter_by(student_id=student.id).all()
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

    logs = db_session.query(ScanLog).filter_by(student_id=student.id).all()
    assert len(logs) == 1, "Duplicate scan should not be added in the database"


def test_scan_next_day_is_not_a_duplicate(client, db_session):
    """
    A student already scanned "yesterday" should be scannable again "today" --
    proves the 409 check is scoped to the current day, not to all-time history.
    """
    student = Student(
        name="Janine", class_="11B", nisn="1122334455", current=True
    )
    db_session.add(student)
    db_session.commit()

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add(
        ScanLog(
            student_id=student.id,
            name=student.name,
            class_=student.class_,
            timestamp=yesterday,
        )
    )
    db_session.commit()

    response = client.post("/scan", json={"nisn": "1122334455"})

    assert response.status_code == 200, "Scan on a new day should succeed"

    logs = db_session.query(ScanLog).filter_by(student_id=student.id).all()
    assert len(logs) == 2, "Should now have yesterday's log plus today's"
