"""
Test suite for POST /classes/bulk, PUT /classes/bulk, POST /classes/bulk-delete

RESPONSE CONTRACT (mirrors /students/bulk -- see BulkClassResponse.py):

Bulk create/update -> 200, body:
{
  "succeeded": [
    {"index": 0, "class": {"class_id": 5, "class_name": ...}},
    ...
  ],
  "failed": [
    {"index": 3, "error": "duplicate class_name", "class": {"class_name": ...}},
    ...
  ]
}

Status code rule: 200 if `succeeded` is non-empty (even with partial failures),
422 only when the batch was non-empty and EVERY row failed. Empty request list
is a no-op, 200, both arrays empty.

Row-level processing rules (create & update) -- same shape as students/nisn,
with class_name as the unique collision key instead of nisn:
  - Malformed row -> per-row failure, siblings still processed.
  - class_name collision WITHIN the same batch -> every row using that
    class_name fails, error "duplicate class_name in batch".
  - class_name collision against an EXISTING DB row -> error
    "duplicate class_name".
  - Empty list -> 200, empty succeeded/failed (no-op), not 422.

Bulk update specifically (per your answers -- same as students/nisn):
  - Rows validated independently; one row's failure doesn't block siblings.
  - class_name collision check happens AFTER computing the full set of
    post-update class_name values for rows passing other validations --
    this is what makes in-batch swaps/rotations (e.g. "10A" <-> "10B")
    legal, backed by the same deferred-constraint approach as nisn.
  - A row resubmitting its own current class_name unchanged is never a
    self-collision.

Bulk delete -> pre-check ALL ids exist before deleting anything (per your
answer -- same all-or-nothing rule as students).
  - all exist  -> delete all, 204, empty body
  - any missing -> 422, body: {"missing_ids": [7, 12]}, nothing deleted
  - duplicate ids deduped before the existence check
  - empty id list -> 204, no-op, nothing deleted

ASSUMPTIONS -- confirm these against your actual schemas/route before trusting
this file wholesale:
  - Create request item: {"class_name": ...}
  - Update request item: {"class_id": ..., "class_name": ...}
  - Delete request: {"ids": [...]} of class_id values
  - Deleting a class with students still assigned to it does NOT fail the
    delete (Class.students relationship is passive_deletes=True, Student.class_id
    is ON DELETE SET NULL) -- see TestBulkDeleteEdgeCases.test_deleting_class_with_students_nulls_their_class_id
"""

from app.models.class_ import Class
from sqlalchemy import select


def make_class_payload(class_name="10A"):
    return {"class_name": class_name}


# ===========================================================================
# 1. BULK CREATE -- POST /classes/bulk
# ===========================================================================
class TestBulkCreate:
    """Happy-path cases: importing a fresh batch of classes."""

    def test_creates_multiple_classes_in_one_request(self, client, db_session):
        """Send N valid class payloads, expect N rows in `succeeded`, zero
        in `failed`, and N new rows actually present in the database."""
        payloads = [make_class_payload(class_name=f"C{i}") for i in range(5)]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 5
        assert len(body["failed"]) == 0

        for item in body["succeeded"]:
            assert "index" in item
            assert "class" in item
            assert "class_id" in item["class"]

        assert sorted(item["index"] for item in body["succeeded"]) == list(range(5))

        db_names = set(db_session.scalars(select(Class.class_name)).all())
        for payload in payloads:
            assert payload["class_name"] in db_names

    def test_created_class_can_be_fetched_afterward(self, client):
        """Bulk-created rows should be indistinguishable from
        individually-created ones -- fetch one back and confirm fields match."""
        payload = make_class_payload(class_name="Fetch Me")

        response = client.post("/classes/bulk", json=[payload])
        assert response.status_code == 200
        created_id = response.json()["succeeded"][0]["class"]["class_id"]

        # ASSUMPTION: GET /classes supports filtering by class_name the same
        # way GET /students filters by nisn. Adjust the params if your route
        # doesn't support this filter.
        get_response = client.get("/classes", params={"class_name": "Fetch Me"})
        assert get_response.status_code == 200
        results = get_response.json()
        assert len(results) == 1
        assert results[0]["class_id"] == created_id
        assert results[0]["class_name"] == "Fetch Me"


class TestBulkCreateEdgeCases:
    def test_empty_list_request(self, client):
        """Empty list -> 200 with empty succeeded/failed (no-op), not 422."""
        response = client.post("/classes/bulk", json=[])

        assert response.status_code == 200
        body = response.json()
        assert body["succeeded"] == []
        assert body["failed"] == []

    def test_duplicate_class_name_against_existing_db_row(self, client, class_factory):
        """One row's class_name already exists in the DB. That row fails,
        others in the batch still succeed. STATUS 200 since succeeded is
        non-empty."""
        class_factory(class_name="Existing")

        payloads = [
            make_class_payload(class_name="Valid A"),
            make_class_payload(class_name="Valid B"),
            make_class_payload(class_name="Existing"),
        ]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 2
        succeeded_indices = {item["index"] for item in body["succeeded"]}
        assert succeeded_indices == {0, 1}

        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 2
        assert body["failed"][0]["error"] == "duplicate class_name"

    def test_duplicate_class_name_within_same_batch(self, client):
        """Two rows in the SAME request use the same class_name, neither
        exists in the DB yet. BOTH fail -- not 'first wins' -- with error
        'duplicate class_name in batch', distinct from the DB-collision
        message. One unrelated valid row still succeeds -> 200."""
        payloads = [
            make_class_payload(class_name="Dupe A"),
            make_class_payload(class_name="Dupe A"),
            make_class_payload(class_name="Valid"),
        ]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 1
        assert body["succeeded"][0]["index"] == 2

        assert len(body["failed"]) == 2
        failed_indices = {item["index"] for item in body["failed"]}
        assert failed_indices == {0, 1}
        for failed_item in body["failed"]:
            assert failed_item["error"] == "duplicate class_name in batch"

    def test_duplicate_class_name_batch_vs_db_have_distinct_errors(self, client, class_factory):
        """Row 0/1 collide with each other (in-batch). Row 2 collides with
        an existing DB row. Different error strings. STATUS 422: all three
        rows fail, succeeded is empty."""
        class_factory(class_name="DupeDb")

        payloads = [
            make_class_payload(class_name="DupePl"),
            make_class_payload(class_name="DupePl"),
            make_class_payload(class_name="DupeDb"),
        ]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 422
        body = response.json()

        assert len(body["succeeded"]) == 0
        assert len(body["failed"]) == 3

        failed_by_index = {item["index"]: item for item in body["failed"]}
        assert failed_by_index[0]["error"] == "duplicate class_name in batch"
        assert failed_by_index[1]["error"] == "duplicate class_name in batch"
        assert failed_by_index[2]["error"] == "duplicate class_name"
        assert failed_by_index[0]["error"] != failed_by_index[2]["error"]

    def test_all_rows_fail_returns_422(self, client, class_factory):
        """CONTRACT PIN: 200-vs-422 is driven by whether `succeeded` is
        empty. A batch where every row fails must 422, mixing a DB
        collision with a malformed row."""
        class_factory(class_name="Existing")

        payloads = [
            make_class_payload(class_name="Existing"),
            {},  # malformed -- missing class_name entirely
        ]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 422
        body = response.json()
        assert body["succeeded"] == []
        assert len(body["failed"]) == 2

    def test_missing_required_field(self, client):
        """One row is missing `class_name` entirely. Per contract this is a
        per-row failure, not a blanket 422, as long as a sibling succeeds."""
        payloads = [
            make_class_payload(class_name="Valid"),
            {},  # no "class_name" key
        ]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 1
        assert body["succeeded"][0]["index"] == 0

        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 1
        assert "error" in body["failed"][0]

    def test_class_name_max_length_violation(self, client):
        """class_name is capped at 10 chars (see Class.class_name /
        FailedClassItem.class_name in BulkClassResponse.py). A row that
        exceeds it should fail per-row, not 500."""
        payloads = [
            make_class_payload(class_name="Valid"),
            make_class_payload(class_name="Way Too Long Name"),
        ]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 1
        assert body["succeeded"][0]["index"] == 0

        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 1

    def test_large_batch_all_valid(self, client, db_session):
        """Smoke test with a bigger batch -- nothing silently truncates."""
        payloads = [make_class_payload(class_name=f"B{i}") for i in range(50)]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 50
        assert len(body["failed"]) == 0

        all_created = db_session.scalars(select(Class).where(Class.class_name.like("B%"))).all()
        assert len(all_created) == 50


class TestBulkCreateResponseShape:
    """Assert the CONTRACT itself -- these catch accidental field renames."""

    def test_response_has_succeeded_and_failed_keys(self, client):
        payloads = [make_class_payload(class_name="Solo")]

        response = client.post("/classes/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()
        assert "succeeded" in body
        assert "failed" in body
        assert isinstance(body["succeeded"], list)
        assert isinstance(body["failed"], list)
        assert body["failed"] == []

    def test_failed_item_includes_input_and_error(self, client, class_factory):
        """Shape of a `failed` entry: "index", "error", "class" (the
        original payload sent -- per FailedClassItem, only class_name).
        STATUS 422: single-row batch, that row fails."""
        class_factory(class_name="Existing")
        bad_payload = make_class_payload(class_name="Existing")

        response = client.post("/classes/bulk", json=[bad_payload])

        assert response.status_code == 422
        body = response.json()
        assert len(body["failed"]) == 1
        failed_item = body["failed"][0]

        assert failed_item["index"] == 0
        assert isinstance(failed_item["error"], str)
        assert failed_item["error"] != ""
        assert failed_item["class"]["class_name"] == bad_payload["class_name"]

    def test_succeeded_item_matches_classresponse_shape(self, client):
        """`succeeded` entry is {"index": ..., "class": {...}} where "class"
        carries ClassResponse fields (class_id, class_name)."""
        payload = make_class_payload(class_name="Shaped")

        response = client.post("/classes/bulk", json=[payload])

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 1
        item = body["succeeded"][0]

        assert set(item.keys()) == {"index", "class"}
        assert item["index"] == 0

        class_ = item["class"]
        assert "class_id" in class_
        assert isinstance(class_["class_id"], int)
        assert class_["class_name"] == "Shaped"


# ===========================================================================
# 2. BULK UPDATE -- PUT /classes/bulk
# ===========================================================================
class TestBulkUpdate:
    def test_updates_multiple_classes(self, client, seeded_students_and_classes, db_session):
        """Happy path: rename several existing classes in one request."""
        classes = db_session.scalars(select(Class)).all()
        target_a, target_b = classes[0], classes[1]

        payload = [
            {"class_id": target_a.class_id, "class_name": "Renamed A"},
            {"class_id": target_b.class_id, "class_name": "Renamed B"},
        ]

        response = client.put("/classes/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 2
        assert len(body["failed"]) == 0

        db_session.expire_all()
        assert db_session.get(Class, target_a.class_id).class_name == "Renamed A"
        assert db_session.get(Class, target_b.class_id).class_name == "Renamed B"

    def test_row_resubmitting_its_own_current_class_name_is_not_a_collision(
        self, client, seeded_students_and_classes, db_session
    ):
        """A row can resend its own unchanged class_name without being
        treated as colliding with itself."""
        target = db_session.scalars(select(Class)).first()

        payload = [{"class_id": target.class_id, "class_name": target.class_name}]

        response = client.put("/classes/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 1
        assert len(body["failed"]) == 0


class TestBulkUpdateEdgeCases:
    def test_one_id_does_not_exist(self, client, seeded_students_and_classes, db_session):
        real_class = db_session.scalars(select(Class)).first()

        payload = [
            {"class_id": real_class.class_id, "class_name": real_class.class_name},
            {"class_id": 999999, "class_name": "Ghost"},
        ]

        response = client.put("/classes/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 1
        assert body["succeeded"][0]["index"] == 0

        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 1

    def test_update_creates_class_name_collision_with_another_row_in_db(
        self, client, seeded_students_and_classes, db_session
    ):
        """Row A renamed to Row B's CURRENT class_name, where B is NOT part
        of this batch. Should fail per-row. STATUS 422: single-row batch."""
        classes = db_session.scalars(select(Class)).all()
        class_a, class_b = classes[0], classes[1]

        payload = [{"class_id": class_a.class_id, "class_name": class_b.class_name}]

        response = client.put("/classes/bulk", json=payload)

        assert response.status_code == 422
        body = response.json()
        assert len(body["succeeded"]) == 0
        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 0
        assert "class_name" in body["failed"][0]["error"].lower()

    def test_two_rows_in_batch_swap_class_names(self, client, seeded_students_and_classes, db_session):
        """Class X currently named 'A', class Y named 'B'. Batch swaps
        them. Per your answer, this needs the same deferred-constraint
        handling as the students nisn swap."""
        classes = db_session.scalars(select(Class)).all()
        class_x, class_y = classes[0], classes[1]
        original_x_name = class_x.class_name
        original_y_name = class_y.class_name

        payload = [
            {"class_id": class_x.class_id, "class_name": original_y_name},
            {"class_id": class_y.class_id, "class_name": original_x_name},
        ]

        response = client.put("/classes/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body.get("failed", [])) == 0
        assert len(body["succeeded"]) == 2

        db_session.expire_all()
        refreshed_x = db_session.get(Class, class_x.class_id)
        refreshed_y = db_session.get(Class, class_y.class_id)

        assert refreshed_x.class_name != refreshed_y.class_name
        assert refreshed_x.class_name == original_y_name
        assert refreshed_y.class_name == original_x_name

    def test_three_way_class_name_rotation(self, client, seeded_students_and_classes, db_session):
        """Generalization of the swap: A<-B, B<-C, C<-A in one batch."""
        classes = db_session.scalars(select(Class)).all()
        class_a, class_b, class_c = classes[0], classes[1], classes[2]
        name_a, name_b, name_c = class_a.class_name, class_b.class_name, class_c.class_name

        payload = [
            {"class_id": class_a.class_id, "class_name": name_b},
            {"class_id": class_b.class_id, "class_name": name_c},
            {"class_id": class_c.class_id, "class_name": name_a},
        ]

        response = client.put("/classes/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body.get("failed", [])) == 0
        assert len(body["succeeded"]) == 3

        db_session.expire_all()
        refreshed_a = db_session.get(Class, class_a.class_id)
        refreshed_b = db_session.get(Class, class_b.class_id)
        refreshed_c = db_session.get(Class, class_c.class_id)

        assert refreshed_a.class_name == name_b
        assert refreshed_b.class_name == name_c
        assert refreshed_c.class_name == name_a
        assert len({refreshed_a.class_name, refreshed_b.class_name, refreshed_c.class_name}) == 3

    def test_swap_succeeds_even_when_sibling_row_fails(self, client, seeded_students_and_classes, db_session):
        """A valid swap plus an unrelated broken row in the same batch --
        the broken row must not roll back the swap."""
        classes = db_session.scalars(select(Class)).all()
        class_x, class_y, class_z = classes[0], classes[1], classes[2]
        original_x_name = class_x.class_name
        original_y_name = class_y.class_name

        payload = [
            {"class_id": class_x.class_id, "class_name": original_y_name},
            {"class_id": class_y.class_id, "class_name": original_x_name},
            {"class_id": class_z.class_id, "class_name": "Way Too Long Name"},  # broken: exceeds max_length
        ]

        response = client.put("/classes/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 2
        succeeded_ids = {item["class"]["class_id"] for item in body["succeeded"]}
        assert succeeded_ids == {class_x.class_id, class_y.class_id}

        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 2

        db_session.expire_all()
        refreshed_x = db_session.get(Class, class_x.class_id)
        refreshed_y = db_session.get(Class, class_y.class_id)
        refreshed_z = db_session.get(Class, class_z.class_id)

        assert refreshed_x.class_name == original_y_name
        assert refreshed_y.class_name == original_x_name
        assert refreshed_z.class_name == classes[2].class_name  # unchanged


class TestBulkUpdateResponseShape:
    def test_response_shape_matches_bulk_create_contract(self, client, seeded_students_and_classes, db_session):
        real_class = db_session.scalars(select(Class)).first()

        payload = [
            {"class_id": real_class.class_id, "class_name": real_class.class_name},
            {"class_id": 999999, "class_name": "Ghost"},
        ]

        response = client.put("/classes/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()

        assert set(body.keys()) == {"succeeded", "failed"}
        assert isinstance(body["succeeded"], list)
        assert isinstance(body["failed"], list)

        assert set(body["succeeded"][0].keys()) == {"index", "class"}
        assert "class_id" in body["succeeded"][0]["class"]

        assert "index" in body["failed"][0]
        assert "error" in body["failed"][0]
        assert "class" in body["failed"][0]


# ===========================================================================
# 3. BULK DELETE -- POST /classes/bulk-delete
# ===========================================================================
# Contract (per your answer): same all-or-nothing pre-check as students.
class TestBulkDelete:
    def test_deletes_multiple_existing_classes(self, client, seeded_students_and_classes, db_session):
        classes = db_session.scalars(select(Class)).all()
        to_delete = classes[:2]
        to_keep = classes[2:]
        delete_ids = [c.class_id for c in to_delete]

        response = client.post("/classes/bulk-delete", json={"ids": delete_ids})

        assert response.status_code == 204
        assert response.content == b""

        for c in to_delete:
            assert db_session.get(Class, c.class_id) is None
        for c in to_keep:
            assert db_session.get(Class, c.class_id) is not None

    def test_deleting_class_with_students_nulls_their_class_id(
        self, client, seeded_students_and_classes, db_session
    ):
        """Class.students is passive_deletes=True and Student.class_id is
        ON DELETE SET NULL -- deleting a class with students assigned
        should succeed, not fail on an FK constraint, and those students'
        class_id should end up NULL afterward."""
        classes = db_session.scalars(select(Class)).all()
        target = classes[0]  # SEED_STUDENTS assigns several students to class_index 0
        target_id = target.class_id

        response = client.post("/classes/bulk-delete", json={"ids": [target_id]})

        assert response.status_code == 204

        db_session.expire_all()
        from app.models.student import Student

        remaining_with_old_class = db_session.scalars(
            select(Student).where(Student.class_id == target_id)
        ).all()
        assert remaining_with_old_class == []


class TestBulkDeleteEdgeCases:
    def test_one_id_does_not_exist_blocks_entire_batch(self, client, seeded_students_and_classes, db_session):
        classes = db_session.scalars(select(Class)).all()
        real_ids = [classes[0].class_id, classes[1].class_id]
        fake_id = 999999

        response = client.post("/classes/bulk-delete", json={"ids": real_ids + [fake_id]})

        assert response.status_code == 422

        for class_id in real_ids:
            assert db_session.get(Class, class_id) is not None

    def test_multiple_missing_ids_all_reported_at_once(self, client, seeded_students_and_classes, db_session):
        real_id = db_session.scalars(select(Class)).first().class_id
        fake_ids = [888888, 999999]

        response = client.post("/classes/bulk-delete", json={"ids": [real_id] + fake_ids})

        assert response.status_code == 422
        body = response.json()
        assert set(body["missing_ids"]) == set(fake_ids)

    def test_empty_id_list(self, client):
        response = client.post("/classes/bulk-delete", json={"ids": []})

        assert response.status_code == 204
        assert response.content == b""

    def test_duplicate_ids_in_same_request(self, client, seeded_students_and_classes, db_session):
        classes = db_session.scalars(select(Class)).all()
        target = classes[0]

        response = client.post(
            "/classes/bulk-delete", json={"ids": [target.class_id, target.class_id, classes[1].class_id]}
        )

        assert response.status_code == 204
        assert db_session.get(Class, target.class_id) is None
        assert db_session.get(Class, classes[1].class_id) is None


class TestBulkDeleteResponseShape:
    def test_success_response_is_empty_204(self, client, seeded_students_and_classes, db_session):
        classes = db_session.scalars(select(Class)).all()
        ids = [c.class_id for c in classes[:2]]

        response = client.post("/classes/bulk-delete", json={"ids": ids})

        assert response.status_code == 204
        assert response.content == b""

    def test_failure_response_shape(self, client, seeded_students_and_classes, db_session):
        real_id = db_session.scalars(select(Class)).first().class_id
        fake_id = 999999

        response = client.post("/classes/bulk-delete", json={"ids": [real_id, fake_id]})

        assert response.status_code == 422
        body = response.json()
        assert set(body.keys()) == {"missing_ids"}
        assert isinstance(body["missing_ids"], list)
        assert fake_id in body["missing_ids"]
