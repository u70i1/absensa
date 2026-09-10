"""
Tests for POST, PUT, DELETE /classes.

Route path and request-schema field names are assumed to mirror the
/students convention (plural resource path, field names matching the
model columns: `grade` and `class_name`). Uniqueness is now on the
(grade, class_name) pair, not on class_name alone -- two classes may
share a name as long as they're in different grades.
"""

import pytest
from app.models.class_ import Class
from sqlalchemy import select

from tests.helpers import make_class_payload

CLASSES_URL = "/classes"


@pytest.fixture()
def existing_class(class_factory):
    return class_factory()


# ---------------------------------------------------------------------------
# POST /classes
# ---------------------------------------------------------------------------


class TestCreateClass:
    def test_create_class_happy_path(self, client, db_session):
        response = client.post(CLASSES_URL, json=make_class_payload())

        assert response.status_code == 201
        body = response.json()
        assert body["class_name"] == "XI-B"
        assert body["grade"] == 10
        assert "class_id" in body

        stmt = select(Class).where(Class.class_name == "XI-B")
        stored = db_session.scalars(stmt).one()
        assert stored.class_name == "XI-B"
        assert stored.grade == 10

    def test_create_class_missing_required_field(self, client):
        response = client.post(CLASSES_URL, json={})
        assert response.status_code == 422

    def test_create_class_missing_grade_rejected(self, client):
        # grade is now a required NOT NULL column -- a payload without it
        # should 422, same as a payload missing class_name.
        response = client.post(CLASSES_URL, json={"class_name": "XI-B"})
        assert response.status_code == 422

    def test_create_class_empty_name_rejected(self, client):
        response = client.post(CLASSES_URL, json=make_class_payload(class_name=""))
        assert response.status_code == 422

    def test_create_class_name_too_long_rejected(self, client):
        # column is String(10) -- one char over should 400/422, not a raw
        # DB error.
        response = client.post(CLASSES_URL, json=make_class_payload(class_name="X" * 11))
        assert response.status_code in (400, 422)

    def test_create_class_name_at_max_length_accepted(self, client):
        response = client.post(CLASSES_URL, json=make_class_payload(class_name="X" * 10))
        assert response.status_code == 201

    def test_create_class_response_does_not_leak_id_control(self, client):
        response = client.post(CLASSES_URL, json=make_class_payload(class_id=99999))
        assert response.status_code == 201
        assert response.json()["class_id"] != 99999

    def test_create_class_duplicate_grade_and_name_rejected(self, client, existing_class):
        response = client.post(
            CLASSES_URL,
            json=make_class_payload(
                class_name=existing_class.class_name, grade=existing_class.grade
            ),
        )
        assert response.status_code in (400, 409)

    def test_create_class_duplicate_grade_and_name_does_not_insert_row(
        self, client, existing_class, db_session
    ):
        client.post(
            CLASSES_URL,
            json=make_class_payload(
                class_name=existing_class.class_name, grade=existing_class.grade
            ),
        )

        stmt = select(Class).where(
            Class.class_name == existing_class.class_name,
            Class.grade == existing_class.grade,
        )
        matches = db_session.scalars(stmt).all()
        assert len(matches) == 1, "Duplicate POST should not create a second row"

    def test_create_class_same_name_different_grade_is_allowed(
        self, client, existing_class
    ):
        # The unique constraint is on (grade, class_name) together, so the
        # same class_name in a different grade is not a collision.
        response = client.post(
            CLASSES_URL,
            json=make_class_payload(
                class_name=existing_class.class_name, grade=existing_class.grade + 1
            ),
        )
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# PUT /classes/{id}
# ---------------------------------------------------------------------------


class TestUpdateClass:
    def test_update_class_happy_path(self, client, existing_class, db_session):
        response = client.put(
            f"{CLASSES_URL}/{existing_class.class_id}",
            json={"grade": existing_class.grade, "class_name": "XII-A rnmd"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["class_name"] == "XII-A rnmd"
        assert body["grade"] == existing_class.grade

        db_session.refresh(existing_class)
        assert existing_class.class_name == "XII-A rnmd"

    def test_update_nonexistent_class_404(self, client):
        response = client.put(
            f"{CLASSES_URL}/999999", json={"grade": 10, "class_name": "Nobody"}
        )
        assert response.status_code == 404

    def test_update_class_cannot_change_id(self, client, existing_class, db_session):
        original_id = existing_class.class_id
        response = client.put(
            f"{CLASSES_URL}/{original_id}",
            json={
                "class_id": original_id + 500,  # attempted spoof
                "grade": existing_class.grade,
                "class_name": existing_class.class_name,
            },
        )
        # either the extra field is ignored (200, id unchanged) or rejected
        # (422) -- it must NOT actually change the primary key
        if response.status_code == 200:
            assert response.json()["class_id"] == original_id
        else:
            assert response.status_code == 422

    def test_update_class_is_idempotent(self, client, existing_class):
        payload = {"grade": existing_class.grade, "class_name": "XII-A"}
        first = client.put(f"{CLASSES_URL}/{existing_class.class_id}", json=payload)
        second = client.put(f"{CLASSES_URL}/{existing_class.class_id}", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()

    def test_update_class_invalid_id_type_422(self, client):
        response = client.put(
            f"{CLASSES_URL}/not-a-number", json={"grade": 10, "class_name": "X"}
        )
        assert response.status_code == 422

    def test_update_class_name_too_long_rejected(self, client, existing_class):
        response = client.put(
            f"{CLASSES_URL}/{existing_class.class_id}",
            json={"grade": existing_class.grade, "class_name": "X" * 11},
        )
        assert response.status_code in (400, 422)

    def test_update_class_duplicate_grade_and_name_rejected(
        self, client, existing_class, class_factory
    ):
        another_class = class_factory(class_name="XI-C", grade=existing_class.grade)

        response = client.put(
            f"{CLASSES_URL}/{another_class.class_id}",
            json={"grade": existing_class.grade, "class_name": existing_class.class_name},
        )
        assert response.status_code in (400, 409)

    def test_update_class_rename_to_own_current_name_is_not_a_conflict(
        self, client, existing_class
    ):
        # A no-op rename (same grade, same class_name) must not be treated
        # as colliding with itself.
        response = client.put(
            f"{CLASSES_URL}/{existing_class.class_id}",
            json={"grade": existing_class.grade, "class_name": existing_class.class_name},
        )
        assert response.status_code == 200

    def test_update_class_rename_to_same_name_different_grade_is_allowed(
        self, client, existing_class, class_factory
    ):
        other_grade_class = class_factory(
            class_name="Shared Name", grade=existing_class.grade + 1
        )

        response = client.put(
            f"{CLASSES_URL}/{existing_class.class_id}",
            json={
                "grade": existing_class.grade,
                "class_name": other_grade_class.class_name,
            },
        )
        assert response.status_code == 200
        assert response.json()["class_name"] == other_grade_class.class_name


# ---------------------------------------------------------------------------
# DELETE /classes/{id}
# ---------------------------------------------------------------------------


class TestDeleteClass:
    def test_delete_class_happy_path(self, client, existing_class, db_session):
        response = client.delete(f"{CLASSES_URL}/{existing_class.class_id}")
        assert response.status_code in (200, 204)

        stmt = select(Class).where(Class.class_id == existing_class.class_id)
        assert db_session.scalars(stmt).one_or_none() is None

    def test_delete_nonexistent_class_404(self, client):
        response = client.delete(f"{CLASSES_URL}/999999")
        assert response.status_code == 404

    def test_delete_class_twice_second_call_404(self, client, existing_class):
        first = client.delete(f"{CLASSES_URL}/{existing_class.class_id}")
        second = client.delete(f"{CLASSES_URL}/{existing_class.class_id}")

        assert first.status_code in (200, 204)
        assert second.status_code == 404

    def test_delete_class_invalid_id_type_422(self, client):
        response = client.delete(f"{CLASSES_URL}/not-a-number")
        assert response.status_code == 422
