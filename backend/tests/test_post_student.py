"""
Tests for POST, PUT, DELETE /students.
"""

import pytest
from app.models.student import Student
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Helpers / fixtures local to this file
# ---------------------------------------------------------------------------


@pytest.fixture
def existing_student(db_session):
    """Insert one student directly via the ORM (bypassing the API) so tests
    have a known row to PUT/DELETE against, independent of POST working."""
    student = Student(name="Ahmad Fauzi", class_="XII-A", nisn="1234567890")
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student


def valid_payload(**overrides):
    """A baseline valid POST body. Override individual fields per test."""
    payload = {
        "name": "Shaun",
        "class_": "XI-B",
        "nisn": "9876543210",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# POST /students
# ---------------------------------------------------------------------------


class TestCreateStudent:
    def test_create_student_happy_path(self, client, db_session):
        response = client.post("/students", json=valid_payload())

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Shaun"
        assert body["class_"] == "XI-B"
        assert body["nisn"] == "9876543210"
        assert "id" in body

        # confirm it's actually in the DB, not just in the response
        stmt = select(Student).where(Student.nisn == "9876543210")
        stored = db_session.scalars(stmt).one()
        assert stored.name == "Shaun"

    def test_create_student_defaults_current_to_true(self, client):
        # your model has current: Mapped[bool] = mapped_column(default=True)
        # — confirm the API surfaces that default rather than leaving it null
        response = client.post("/students", json=valid_payload())
        assert response.status_code == 201
        assert response.json()["current"] is True

    def test_create_student_duplicate_nisn_rejected(self, client, existing_student):
        response = client.post(
            "/students", json=valid_payload(nisn=existing_student.nisn)
        )
        # DECISION: pick 400 or 409 and stay consistent — this just checks
        # you didn't let it 500 or silently succeed with a duplicate.
        assert response.status_code in (400, 409)

    def test_create_student_missing_required_field(self, client):
        payload = valid_payload()
        del payload["name"]
        response = client.post("/students", json=payload)
        assert response.status_code == 422

    def test_create_student_missing_nisn(self, client):
        payload = valid_payload()
        del payload["nisn"]
        response = client.post("/students", json=payload)
        assert response.status_code == 422

    def test_create_student_class_too_long(self, client):
        # column is String(10) — anything over that should fail cleanly,
        # not 500 with a raw psycopg2/DataError traceback
        response = client.post("/students", json=valid_payload(class_="X" * 11))
        assert response.status_code in (400, 422)

    def test_create_student_empty_name_rejected(self, client):
        # empty string currently satisfies "is a str" — decide if that's
        # actually valid for your domain. This test documents the decision;
        # flip the assertion if you deliberately want to allow it.
        response = client.post("/students", json=valid_payload(name=""))
        assert response.status_code == 422

    def test_create_student_response_does_not_leak_id_control(self, client):
        # posting an id in the body shouldn't let the client pick their own PK
        response = client.post("/students", json=valid_payload(id=99999))
        assert response.status_code == 201
        assert response.json()["id"] != 99999


# ---------------------------------------------------------------------------
# PUT /students/{id}
# ---------------------------------------------------------------------------


class TestUpdateStudent:
    def test_update_student_happy_path(self, client, existing_student, db_session):
        response = client.put(
            f"/students/{existing_student.id}",
            json={"name": "Bitzer Updated", "class_": "XII-A", "nisn": "1234567890"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Bitzer Updated"

        db_session.refresh(existing_student)
        assert existing_student.name == "Bitzer Updated"

    def test_update_nonexistent_student_404(self, client):
        response = client.put(
            "/students/999999",
            json={"name": "Nobody", "class_": "X-A", "nisn": "0000000000"},
        )
        assert response.status_code == 404

    def test_update_student_cannot_change_id(self, client, existing_student, db_session):
        original_id = existing_student.id
        response = client.put(
            f"/students/{original_id}",
            json={
                "id": original_id + 500,  # attempted spoof
                "name": existing_student.name,
                "class_": existing_student.class_,
                "nisn": existing_student.nisn,
            },
        )
        # either the extra field is ignored (200, id unchanged) or rejected
        # (422) — what it must NOT do is actually change the primary key
        if response.status_code == 200:
            assert response.json()["id"] == original_id
        else:
            assert response.status_code == 422

    def test_update_student_duplicate_nisn_conflicts(self, client, db_session, existing_student):
        other = Student(name="Other Student", class_="X-C", nisn="1111111111")
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        response = client.put(
            f"/students/{other.id}",
            json={"name": other.name, "class_": other.class_, "nisn": existing_student.nisn},
        )
        assert response.status_code in (400, 409)

    def test_update_student_is_idempotent(self, client, existing_student):
        payload = {"name": "Bitzer", "class_": "XII-A", "nisn": "1234567890"}
        first = client.put(f"/students/{existing_student.id}", json=payload)
        second = client.put(f"/students/{existing_student.id}", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()

    def test_update_student_invalid_id_type_422(self, client):
        response = client.put(
            "/students/not-a-number",
            json={"name": "X", "class_": "X", "nisn": "0000000001"},
        )
        assert response.status_code == 422


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

    @pytest.mark.skip(
        reason="TODO: fill in once you've decided FK behavior for scan_logs "
        "on student delete (cascade delete vs. restrict-with-409). "
        "Insert a ScanLog tied to `existing_student`, delete the student, "
        "then assert whichever behavior you intended actually happens."
    )
    def test_delete_student_with_scan_logs(self, client, existing_student, db_session):
        pass
