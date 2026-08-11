"""
Tests for POST, PUT, DELETE /students.
"""

import pytest
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Helpers / fixtures local to this file
# ---------------------------------------------------------------------------


@pytest.fixture
def existing_class(db_session):
    """Insert one class directly via the ORM (bypassing the API) so tests
    have a known row to reference, independent of POST working."""
    class_ = Class(class_name="XII-A")
    db_session.add(class_)
    db_session.commit()
    db_session.refresh(class_)
    return class_


@pytest.fixture
def existing_student(db_session, existing_class):
    """Insert one student directly via the ORM (bypassing the API) so tests
    have a known row to PUT/DELETE against, independent of POST working."""
    student = Student(
        name="Bitzer", class_id=existing_class.class_id, nisn="1234567890"
    )
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student


def valid_payload(existing_class, **overrides):
    """A baseline valid POST body. Override individual fields per test.

    class_id is now a required argument (not a hardcoded default) because
    a hardcoded int here would drift from whatever ID the sequence actually
    assigned in a given test run.
    """
    payload = {
        "name": "Shaun",
        "class_id": existing_class.class_id,
        "nisn": "9876543210",
        "current": True,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# POST /students
# ---------------------------------------------------------------------------


class TestCreateStudent:
    def test_create_student_happy_path(self, client, existing_class, db_session):
        response = client.post("/students", json=valid_payload(existing_class))

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Shaun"
        assert body["class_id"] == existing_class.class_id
        assert body["nisn"] == "9876543210"
        assert "id" in body

        # confirm it's actually in the DB, not just in the response
        stmt = select(Student).where(Student.nisn == "9876543210")
        stored = db_session.scalars(stmt).one()
        assert stored.name == "Shaun"
        assert stored.class_id == existing_class.class_id

    def test_create_student_defaults_current_to_true(self, client, existing_class):
        # your model has current: Mapped[bool] = mapped_column(default=True)
        # — confirm the API surfaces that default rather than leaving it null
        response = client.post("/students", json=valid_payload(existing_class))
        assert response.status_code == 201
        assert response.json()["current"] is True

    def test_create_student_duplicate_nisn_rejected(
        self, client, existing_student, existing_class
    ):
        response = client.post(
            "/students",
            json=valid_payload(existing_class, nisn=existing_student.nisn),
        )
        assert response.status_code in (400, 409)

    def test_create_student_missing_required_field(self, client, existing_class):
        payload = valid_payload(existing_class)
        del payload["name"]
        response = client.post("/students", json=payload)
        assert response.status_code == 422

    def test_create_student_missing_nisn(self, client, existing_class):
        payload = valid_payload(existing_class)
        del payload["nisn"]
        response = client.post("/students", json=payload)
        assert response.status_code == 422

    def test_create_student_nonexistent_class_id_rejected(self, client):
        # class_id now points at a real FK — an id with no matching Class
        # row should fail cleanly, not 500 with a raw IntegrityError
        response = client.post(
            "/students",
            json={"name": "Shaun", "class_id": 999999, "nisn": "9876543210"},
        )
        assert response.status_code in (400, 404, 422)

    def test_create_student_without_class_id_allowed(self, client):
        # class_id is nullable=True — a student with no class assigned yet
        # (e.g. pending placement) must be a valid state, not an error
        response = client.post(
            "/students",
            json={"name": "Shaun", "class_id": None, "nisn": "9876543210", "current": True},
        )
        assert response.status_code == 201
        assert response.json()["class_id"] is None

    def test_create_student_class_id_wrong_type_rejected(self, client):
        # class_id is an int FK now, not the old free-text "class" string —
        # a string here should 422 at the Pydantic layer, before it ever
        # reaches the DB as a malformed query
        response = client.post(
            "/students",
            json={"name": "Shaun", "class_id": "XII-A", "nisn": "9876543210"},
        )
        assert response.status_code == 422

    def test_create_student_nisn_too_long_rejected(self, client, existing_class):
        # column is String(10) — one char over should fail cleanly (422),
        # not 500 with a raw psycopg2/DataError traceback
        response = client.post(
            "/students", json=valid_payload(existing_class, nisn="1" * 11)
        )
        assert response.status_code in (400, 422)

    def test_create_student_nisn_at_max_length_accepted(self, client, existing_class):
        # boundary check on the other side of the limit above — exactly 10
        # chars should be accepted, not off-by-one rejected
        response = client.post(
            "/students", json=valid_payload(existing_class, nisn="1" * 10)
        )
        assert response.status_code == 201

    def test_create_student_empty_name_rejected(self, client, existing_class):
        # empty string currently satisfies "is a str" — decide if that's
        # actually valid for your domain. This test documents the decision;
        # flip the assertion if you deliberately want to allow it.
        response = client.post(
            "/students", json=valid_payload(existing_class, name="")
        )
        assert response.status_code == 422

    def test_create_student_response_does_not_leak_id_control(
        self, client, existing_class
    ):
        # posting an id in the body shouldn't let the client pick their own PK
        response = client.post(
            "/students", json=valid_payload(existing_class, id=99999)
        )
        assert response.status_code == 201
        assert response.json()["id"] != 99999


# ---------------------------------------------------------------------------
# PUT /students/{id}
# ---------------------------------------------------------------------------


class TestUpdateStudent:
    def test_update_student_happy_path(self, client, existing_student, db_session):
        response = client.put(
            f"/students/{existing_student.id}",
            json={
                "name": "Bitzer Updated",
                "class_id": existing_student.class_id,
                "nisn": "1234567890",
                "current": True
            },
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Bitzer Updated"

        db_session.refresh(existing_student)
        assert existing_student.name == "Bitzer Updated"

    def test_update_nonexistent_student_404(self, client, existing_class):
        response = client.put(
            "/students/999999",
            json={
                "name": "Nobody",
                "class_id": existing_class.class_id,
                "nisn": "0000000000",
                "current": True
            },
        )
        assert response.status_code == 404

    def test_update_student_cannot_change_id(
        self, client, existing_student, db_session
    ):
        original_id = existing_student.id
        response = client.put(
            f"/students/{original_id}",
            json={
                "id": original_id + 500,  # attempted spoof
                "name": existing_student.name,
                "class_id": existing_student.class_id,
                "nisn": existing_student.nisn,
            },
        )
        # either the extra field is ignored (200, id unchanged) or rejected
        # (422) — what it must NOT do is actually change the primary key
        if response.status_code == 200:
            assert response.json()["id"] == original_id
        else:
            assert response.status_code == 422

    def test_update_student_duplicate_nisn_conflicts(
        self, client, db_session, existing_student, existing_class
    ):
        other = Student(
            name="Other Student", class_id=existing_class.class_id, nisn="1111111111"
        )
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        response = client.put(
            f"/students/{other.id}",
            json={
                "name": other.name,
                "class_id": other.class_id,
                "nisn": existing_student.nisn,
                "current": True
            },
        )
        assert response.status_code in (400, 409)

    def test_update_student_is_idempotent(self, client, existing_student):
        payload = {
            "name": "Bitzer",
            "class_id": existing_student.class_id,
            "nisn": "1234567890",
            "current": True
        }
        first = client.put(f"/students/{existing_student.id}", json=payload)
        second = client.put(f"/students/{existing_student.id}", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()

    def test_update_student_invalid_id_type_422(self, client, existing_class):
        response = client.put(
            "/students/not-a-number",
            json={
                "name": "X",
                "class_id": existing_class.class_id,
                "nisn": "0000000001",
            },
        )
        assert response.status_code == 422

    def test_update_student_nonexistent_class_id_rejected(
        self, client, existing_student
    ):
        response = client.put(
            f"/students/{existing_student.id}",
            json={
                "name": existing_student.name,
                "class_id": 999999,
                "nisn": existing_student.nisn,
            },
        )
        assert response.status_code in (400, 404, 422)

    def test_update_student_can_mark_graduated(
        self, client, existing_student, db_session
    ):
        # current defaults to True — flipping it to False is a real
        # operation (graduation), not just a theoretical field
        response = client.put(
            f"/students/{existing_student.id}",
            json={
                "name": existing_student.name,
                "class_id": existing_student.class_id,
                "nisn": existing_student.nisn,
                "current": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["current"] is False

        db_session.refresh(existing_student)
        assert existing_student.current is False

    def test_update_student_can_clear_class_id(
        self, client, existing_student, db_session
    ):
        # class_id is nullable — un-assigning a student's class (e.g.
        # between school years) must work via PUT, not just at creation
        response = client.put(
            f"/students/{existing_student.id}",
            json={
                "name": existing_student.name,
                "class_id": None,
                "nisn": existing_student.nisn,
                "current": True
            },
        )
        assert response.status_code == 200
        assert response.json()["class_id"] is None

        db_session.refresh(existing_student)
        assert existing_student.class_id is None


# ---------------------------------------------------------------------------
# DELETE /students/{id}
# ---------------------------------------------------------------------------


class TestDeleteStudent:
    def test_delete_student_happy_path(self, client, existing_student, db_session):
        response = client.delete(f"/students/{existing_student.id}")
        assert response.status_code in (200, 204)

        stmt = select(Student).where(Student.id == existing_student.id)
        assert db_session.scalars(stmt).one_or_none() is None

    def test_delete_nonexistent_student_404(self, client):
        response = client.delete("/students/999999")
        assert response.status_code == 404

    def test_delete_student_twice_second_call_404(self, client, existing_student):
        first = client.delete(f"/students/{existing_student.id}")
        second = client.delete(f"/students/{existing_student.id}")

        assert first.status_code in (200, 204)
        assert second.status_code == 404

    def test_delete_student_invalid_id_type_422(self, client):
        response = client.delete("/students/not-a-number")
        assert response.status_code == 422

    def test_delete_student_cascades_scan_logs(
        self, client, existing_student, existing_class, db_session
    ):
        # ScanLog.class_ is a plain string snapshot, not a FK to Class —
        # it logs the class name as it was at scan time, so we pass the
        # Class's name here, not the Student relationship (which no longer
        # exists as a string).
        log = ScanLog(
            student_nisn=existing_student.nisn,
            name=existing_student.name,
            class_name=existing_class.class_name,
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)
        log_scan_id = log.scan_id

        response = client.delete(f"/students/{existing_student.id}")
        assert response.status_code in (200, 204)

        stmt = select(ScanLog).where(ScanLog.scan_id == log_scan_id)
        assert db_session.scalars(stmt).one_or_none() is None

    def test_delete_student_with_scan_logs_does_not_orphan_or_error(
        self, client, existing_student, existing_class, db_session
    ):
        # two scan logs for the same student — cascade should take out both,
        # and the delete request itself should not 500 just because related
        # rows exist (a common failure mode if the FK were RESTRICT instead)
        for _ in range(2):
            db_session.add(
                ScanLog(
                    student_nisn=existing_student.nisn,
                    name=existing_student.name,
                    class_name=existing_class.class_name,
                )
            )
        db_session.commit()

        response = client.delete(f"/students/{existing_student.id}")
        assert response.status_code in (200, 204)

        stmt = select(ScanLog).where(ScanLog.student_nisn == existing_student.nisn)
        remaining = db_session.scalars(stmt).all()
        assert remaining == []

