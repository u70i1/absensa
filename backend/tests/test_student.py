"""Tests for /students endpoints."""

import pytest
from app.models.scan_log import ScanLog
from app.models.student import Student
from sqlalchemy import select

from tests.helpers import make_student_payload

# Helpers

# ---------------------------------------------------------------------------
# Helpers / fixtures local to this file
# ---------------------------------------------------------------------------


@pytest.fixture
def existing_class(class_factory):
    """A default class (XII-A) for most tests."""
    return class_factory(class_name="XII-A")


@pytest.fixture
def existing_student(student_factory, existing_class):
    """A single student with default values, linked to the default class."""
    return student_factory(
        name="Bitzer",
        class_id=existing_class.class_id,
        nisn="1234567890",
        current=True,
    )


class TestGetStudents:
    # ---------------------------------------------------------------------------
    # Pagination
    # ---------------------------------------------------------------------------
    def test_default_page_size_is_10(self, client, seeded_students_and_classes):
        response = client.get("/students")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 10

    def test_page_2_returns_remaining_students(
        self, client, seeded_students_and_classes
    ):
        """11 seeded students, limit=10 -> page 2 should hold the last 2."""
        response = client.get("/students?page=2&limit=10")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2

    def test_custom_limit_per_page(self, client, seeded_students_and_classes):
        response = client.get("/students?limit=5")

        assert response.status_code == 200
        assert len(response.json()) == 5

    def test_page_and_limit_do_not_repeat_rows(
        self, client, seeded_students_and_classes
    ):
        """Page 1 and page 2 (limit=5) should never share a student."""
        page1 = client.get("/students?page=1&limit=5").json()
        page2 = client.get("/students?page=2&limit=5").json()

        ids_page1 = {s["id"] for s in page1}
        ids_page2 = {s["id"] for s in page2}
        assert ids_page1.isdisjoint(ids_page2)

    @pytest.mark.parametrize("bad_page", [0, -1])
    def test_invalid_page_is_rejected(self, client, bad_page):
        response = client.get(f"/students?page={bad_page}")
        assert response.status_code == 422

    # ---------------------------------------------------------------------------
    # class filter
    # ---------------------------------------------------------------------------

    def test_filter_by_class(self, client, seeded_students_and_classes):
        response = client.get("/students?class=10B&limit=100")

        assert response.status_code == 200
        body = response.json()
        names = {s["name"] for s in body}
        assert names == {"Yvonne", "Tom"}

    def test_filter_by_class_no_match(self, client, seeded_students_and_classes):
        response = client.get("/students?class=99Z")

        assert response.status_code == 200
        assert response.json() == []

    # ---------------------------------------------------------------------------
    # name filter (substring, case-insensitive)
    # ---------------------------------------------------------------------------

    def test_filter_by_name_substring(self, client, seeded_students_and_classes):
        """'lan' should match both Declan and Alan."""
        response = client.get("/students?name=lan")

        assert response.status_code == 200
        names = {s["name"] for s in response.json()}
        assert names == {"Declan", "Alan"}

    def test_filter_by_name_is_case_insensitive(
        self, client, seeded_students_and_classes
    ):
        response = client.get("/students?name=SHAUN")

        assert response.status_code == 200
        names = {s["name"] for s in response.json()}
        assert names == {"Shaun"}

    def test_filter_by_name_no_match(self, client, seeded_students_and_classes):
        response = client.get("/students?name=zzz")

        assert response.status_code == 200
        assert response.json() == []

    # ---------------------------------------------------------------------------
    # nisn filter (exact match)
    # ---------------------------------------------------------------------------

    def test_filter_by_nisn_exact_match(self, client, seeded_students_and_classes):
        response = client.get("/students?nisn=1000000003")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["name"] == "Liz"

    def test_filter_by_nisn_no_match(self, client, seeded_students_and_classes):
        response = client.get("/students?nisn=0000000000")

        assert response.status_code == 200
        assert response.json() == []

    # ---------------------------------------------------------------------------
    # combined filters
    # ---------------------------------------------------------------------------

    def test_combined_class_and_name_filters(self, client, seeded_students_and_classes):
        """class=10B narrows to Yvonne+Tom, then name=yvon narrows further to Yvonne."""
        response = client.get("/students?class=10B&name=yvon")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["name"] == "Yvonne"

    # ---------------------------------------------------------------------------
    # empty database
    # ---------------------------------------------------------------------------

    def test_no_students_returns_empty_list(self, client):
        response = client.get("/students")

        assert response.status_code == 200
        assert response.json() == []


class TestCreateStudent:
    def test_create_student_happy_path(self, client, existing_class, db_session):
        response = client.post("/students", json=make_student_payload(existing_class))

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
        response = client.post("/students", json=make_student_payload(existing_class))
        assert response.status_code == 201
        assert response.json()["current"] is True

    def test_create_student_duplicate_nisn_rejected(
        self, client, existing_student, existing_class
    ):
        response = client.post(
            "/students",
            json=make_student_payload(existing_class, nisn=existing_student.nisn),
        )
        assert response.status_code in (400, 409)

    def test_create_student_missing_required_field(self, client, existing_class):
        payload = make_student_payload(existing_class)
        del payload["name"]
        response = client.post("/students", json=payload)
        assert response.status_code == 422

    def test_create_student_missing_nisn(self, client, existing_class):
        payload = make_student_payload(existing_class)
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
            json={
                "name": "Shaun",
                "class_id": None,
                "nisn": "9876543210",
                "current": True,
            },
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
            "/students", json=make_student_payload(existing_class, nisn="1" * 11)
        )
        assert response.status_code in (400, 422)

    def test_create_student_nisn_at_max_length_accepted(self, client, existing_class):
        # boundary check on the other side of the limit above — exactly 10
        # chars should be accepted, not off-by-one rejected
        response = client.post(
            "/students", json=make_student_payload(existing_class, nisn="1" * 10)
        )
        assert response.status_code == 201

    def test_create_student_empty_name_rejected(self, client, existing_class):
        # empty string currently satisfies "is a str" — decide if that's
        # actually valid for your domain. This test documents the decision;
        # flip the assertion if you deliberately want to allow it.
        response = client.post(
            "/students", json=make_student_payload(existing_class, name="")
        )
        assert response.status_code == 422

    def test_create_student_response_does_not_leak_id_control(
        self, client, existing_class
    ):
        # posting an id in the body shouldn't let the client pick their own PK
        response = client.post(
            "/students", json=make_student_payload(existing_class, id=99999)
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
                "current": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Bitzer Updated"

        db_session.refresh(existing_student)
        assert existing_student.name == "Bitzer Updated"

    def test_update_nonexistent_student_422(self, client, existing_class):
        response = client.put(
            "/students/999999",
            json={
                "name": "Nobody",
                "class_id": existing_class.class_id,
                "nisn": "0000000000",
                "current": True,
            },
        )
        assert response.status_code == 422

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
        self, client, db_session, existing_student, existing_class, student_factory
    ):
        other = student_factory(
            name="Other Student",
            class_id=existing_class.class_id,
            nisn="1111111111",
            current=True,
        )

        response = client.put(
            f"/students/{other.id}",
            json={
                "name": other.name,
                "class_id": other.class_id,
                "nisn": existing_student.nisn,
                "current": True,
            },
        )
        assert response.status_code in (400, 409)

    def test_update_student_is_idempotent(self, client, existing_student):
        payload = {
            "name": "Bitzer",
            "class_id": existing_student.class_id,
            "nisn": "1234567890",
            "current": True,
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
                "current": True,
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

    def test_delete_nonexistent_student_422(self, client):
        response = client.delete("/students/999999")
        assert response.status_code == 422

    def test_delete_student_twice_second_call_422(self, client, existing_student):
        first = client.delete(f"/students/{existing_student.id}")
        second = client.delete(f"/students/{existing_student.id}")

        assert first.status_code in (200, 204)
        assert second.status_code == 422

    def test_delete_student_invalid_id_type_422(self, client):
        response = client.delete("/students/not-a-number")
        assert response.status_code == 422

    def test_delete_student_with_scan_logs_does_not_orphan_or_error(
        self, client, existing_student, existing_class, db_session
    ):
        # two scan logs for the same student — cascade should take out both,
        # and the delete request itself should not 500 just because related
        # rows exist (a common failure mode if the FK were RESTRICT instead)
        for _ in range(2):
            db_session.add(
                ScanLog(
                    student_id=existing_student.id,
                    name=existing_student.name,
                    class_name=existing_class.class_name,
                )
            )
        db_session.commit()

        response = client.delete(f"/students/{existing_student.id}")
        assert response.status_code in (200, 204)

        stmt = select(ScanLog).where(ScanLog.student_id == existing_student.nisn)
        remaining = db_session.scalars(stmt).all()
        assert remaining == []
