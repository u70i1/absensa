"""
Tests for POST, PUT, DELETE /classes.

Route path and request-schema field names are assumed to mirror the
/students convention (plural resource path, field names matching the
model columns). If your actual router uses `/class` (singular) or a
schema field other than `class_name`, update the constants below —
everything else derives from them.
"""

import pytest
from app.models.class_ import Class
from sqlalchemy import select

from tests.helpers import make_class_payload

CLASSES_URL = "/classes"


# ---------------------------------------------------------------------------
# Helpers / fixtures local to this file
# ---------------------------------------------------------------------------

@pytest.fixture()
def existing_class(class_factory):
    class_ = class_factory()
    return class_

# ---------------------------------------------------------------------------
# POST /classes
# ---------------------------------------------------------------------------


class TestCreateClass:
    def test_create_class_happy_path(self, client, db_session):
        response = client.post(CLASSES_URL, json=make_class_payload())

        assert response.status_code == 201
        body = response.json()
        assert body["class_name"] == "XI-B"
        assert "class_id" in body

        stmt = select(Class).where(Class.class_name == "XI-B")
        stored = db_session.scalars(stmt).one()
        assert stored.class_name == "XI-B"

    def test_create_class_missing_required_field(self, client):
        response = client.post(CLASSES_URL, json={})
        assert response.status_code == 422

    def test_create_class_empty_name_rejected(self, client):
        # empty string satisfies "is a str" at the type level — decide if
        # that's actually valid for your domain, same call as the analogous
        # empty-name test on Student. Flip this if you deliberately allow it.
        response = client.post(CLASSES_URL, json=make_class_payload(class_name=""))
        assert response.status_code == 422

    def test_create_class_name_too_long_rejected(self, client):
        # column is String(10) — one char over should fail cleanly (422),
        # not 500 with a raw psycopg2/DataError traceback
        response = client.post(CLASSES_URL, json=make_class_payload(class_name="X" * 11))
        assert response.status_code in (400, 422)

    def test_create_class_name_at_max_length_accepted(self, client):
        # boundary check on the other side of the limit above
        response = client.post(CLASSES_URL, json=make_class_payload(class_name="X" * 10))
        assert response.status_code == 201

    def test_create_class_response_does_not_leak_id_control(self, client):
        # posting a class_id in the body shouldn't let the client pick
        # their own PK
        response = client.post(CLASSES_URL, json=make_class_payload(class_id=99999))
        assert response.status_code == 201
        assert response.json()["class_id"] != 99999

    def test_create_class_duplicate_name_rejected(self, client, existing_class):
        response = client.post(
            CLASSES_URL, json=make_class_payload(class_name=existing_class.class_name)
        )
        assert response.status_code in (400, 409)

    def test_create_class_duplicate_name_does_not_insert_row(
        self, client, existing_class, db_session
    ):
        # belt-and-suspenders on the test above: confirm the rejected
        # duplicate never actually landed in the DB, in case the endpoint
        # returns an error status but still commits (a real failure mode
        # if the constraint check and the insert aren't in the same
        # transaction/are handled out of order)
        client.post(
            CLASSES_URL, json=make_class_payload(class_name=existing_class.class_name)
        )

        stmt = select(Class).where(Class.class_name == existing_class.class_name)
        matches = db_session.scalars(stmt).all()
        assert len(matches) == 1, "Duplicate POST should not create a second row"


# ---------------------------------------------------------------------------
# PUT /classes/{id}
# ---------------------------------------------------------------------------


class TestUpdateClass:
    def test_update_class_happy_path(self, client, existing_class, db_session):
        response = client.put(
            f"{CLASSES_URL}/{existing_class.class_id}",
            json={"class_name": "XII-A rnmd"},
        )
        assert response.status_code == 200
        assert response.json()["class_name"] == "XII-A rnmd"

        db_session.refresh(existing_class)
        assert existing_class.class_name == "XII-A rnmd"

    def test_update_nonexistent_class_404(self, client):
        response = client.put(f"{CLASSES_URL}/999999", json={"class_name": "Nobody"})
        assert response.status_code == 404

    def test_update_class_cannot_change_id(self, client, existing_class, db_session):
        original_id = existing_class.class_id
        response = client.put(
            f"{CLASSES_URL}/{original_id}",
            json={
                "class_id": original_id + 500,  # attempted spoof
                "class_name": existing_class.class_name,
            },
        )
        # either the extra field is ignored (200, id unchanged) or rejected
        # (422) — what it must NOT do is actually change the primary key
        if response.status_code == 200:
            assert response.json()["class_id"] == original_id
        else:
            assert response.status_code == 422

    def test_update_class_is_idempotent(self, client, existing_class):
        payload = {"class_name": "XII-A"}
        first = client.put(f"{CLASSES_URL}/{existing_class.class_id}", json=payload)
        second = client.put(f"{CLASSES_URL}/{existing_class.class_id}", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()

    def test_update_class_invalid_id_type_422(self, client):
        response = client.put(f"{CLASSES_URL}/not-a-number", json={"class_name": "X"})
        assert response.status_code == 422

    def test_update_class_name_too_long_rejected(self, client, existing_class):
        response = client.put(
            f"{CLASSES_URL}/{existing_class.class_id}",
            json={"class_name": "X" * 11},
        )
        assert response.status_code in (400, 422)

    def test_update_class_duplicate_name_rejected(
        self, client, existing_class, class_factory
    ):
        another_class = class_factory(class_name="XI-C")

        response = client.put(
            f"{CLASSES_URL}/{another_class.class_id}",
            json={"class_name": existing_class.class_name},
        )
        assert response.status_code in (400, 409)

    def test_update_class_rename_to_own_current_name_is_not_a_conflict(
        self, client, existing_class
    ):
        # renaming a class to the name it already has must NOT be treated
        # as a collision with itself — a naive "does this name exist
        # anywhere" check (instead of "does it exist on a DIFFERENT row")
        # would wrongly 409 this no-op update
        response = client.put(
            f"{CLASSES_URL}/{existing_class.class_id}",
            json={"class_name": existing_class.class_name},
        )
        assert response.status_code == 200


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

    # Delete-with-students-attached (the SET NULL contract) is already
    # covered in test_students.py::TestDeleteClassWithStudents — not
    # duplicated here to avoid two tests asserting the same DB-level
    # behavior from opposite ends of the relationship.
