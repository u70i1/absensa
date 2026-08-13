"""
Test suite for POST /students/bulk, PATCH /students/bulk, POST /students/bulk-delete

RESPONSE CONTRACT:

Bulk create/update -> 200, body:
{
  "succeeded": [
    {"index": 0, "student": {"id": 5, "name": ..., "nisn": ..., "class_id": ..., "current": ...}},
    ...
  ],
  "failed": [
    {"index": 3, "error": "duplicate nisn", "student": {"name": ..., "nisn": ..., "class_id": ...}},
    ...
  ]
}

Both branches share "index" so a frontend can zip either array back to the
original spreadsheet row without special-casing. The nested keys are
deliberately named for what they contain rather than reused across
branches:
  - succeeded[i]["student"] is the resulting StudentResponse (has "id",
    reflects anything the server defaulted/normalized).
  - failed[i]["student"] is the original request payload as sent (no "id",
    since it never made it into the DB) -- useful for a spreadsheet UI to
    show the user exactly what they typed on the offending row.

Row-level processing rules (create & update):
  - Malformed row (missing required field, wrong type) -> validation happens
    manually per-row (request body is typed loosely enough that one bad row
    does not 422 the whole request) -> that row goes to `failed`, siblings
    still processed.
  - nisn collision WITHIN the same batch (not yet in DB) -> Python
    pre-scans the batch's nisns before touching SQLAlchemy. If a nisn
    appears more than once in the incoming batch, EVERY row using that
    nisn fails (not "first wins") -> error "duplicate nisn in batch".
    This is intentionally distinct from...
  - nisn collision against an EXISTING DB row -> error "duplicate nisn".
    Different message because it's a different fix for the user (one is
    "you typed it twice", the other is "this student already exists").
  - Valid rows are committed; failures are filtered out and reported.
  - Empty list -> 200, empty succeeded/failed (no-op), not 422.

Bulk delete -> pre-check ALL ids exist before deleting anything.
  - all exist  -> delete all, 204, empty body
  - any missing -> 404, body: {"missing_ids": [7, 12]}, nothing deleted
  - duplicate ids in the request are deduped before the existence check,
    so [5, 5, 7] behaves identically to [5, 7]
  - empty id list -> 204, no-op, nothing deleted

Suggested schema names (adjust to match whatever you actually name them):
  - StudentBulkCreateRequest = list[StudentRequest]
  - StudentBulkUpdateItem    = StudentRequest + an `id` field
  - StudentBulkDeleteRequest = {"ids": list[int]}
"""

from app.models.student import Student
from sqlalchemy import select


def make_student_payload(name="Shaun", nisn="1000000001", class_id=None, current=True):
    return {"name": name, "nisn": nisn, "class_id": class_id, "current": current}


# ===========================================================================
# 1. BULK CREATE -- POST /students/bulk
# ===========================================================================
class TestBulkCreate:
    """Cases matching how a teacher would actually use this: importing a
    fresh batch of students from a spreadsheet, all valid rows."""

    def test_creates_multiple_students_in_one_request(self, client, class_factory, db_session):
        """Happy path. Send N valid student payloads, expect N rows in
        `succeeded`, zero in `failed`, and N new rows actually present in
        the database afterward."""
        class_ = class_factory()
        payloads = [
            make_student_payload(name=f"Student {i}", nisn=f"100000{i:04d}", class_id=class_.class_id)
            for i in range(5)
        ]

        response = client.post("/students/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 5
        assert len(body["failed"]) == 0

        for item in body["succeeded"]:
            assert "index" in item
            assert "student" in item
            assert "id" in item["student"]

        # Confirm indices map 1:1 with input order
        assert sorted(item["index"] for item in body["succeeded"]) == list(range(5))

        # Don't just trust the response -- check the DB directly
        db_nisns = set(db_session.scalars(select(Student.nisn)).all())
        for payload in payloads:
            assert payload["nisn"] in db_nisns

    def test_created_student_can_be_fetched_afterward(self, client, class_factory):
        """Sanity check that bulk-created rows are indistinguishable from
        individually-created ones -- fetch one back via GET /students and
        confirm the fields match what you sent."""
        class_ = class_factory()
        class_id = class_.class_id
        payload = make_student_payload(name="Fetch Me", nisn="1000009999", class_id=class_id)

        response = client.post("/students/bulk", json=[payload])
        assert response.status_code == 200
        created_id = response.json()["succeeded"][0]["student"]["id"]

        get_response = client.get("/students", params={"nisn": "1000009999"})
        assert get_response.status_code == 200
        results = get_response.json()
        assert len(results) == 1
        fetched = results[0]
        assert fetched["id"] == created_id
        assert fetched["name"] == "Fetch Me"
        assert fetched["nisn"] == "1000009999"
        assert fetched["class_id"] == class_id

    def test_students_without_class_id_are_allowed(self, client, db_session):
        """class_id is nullable on the model. A bulk import of students who
        haven't been assigned a class yet should succeed with class_id=None."""
        payloads = [
            make_student_payload(name="No Class A", nisn="1000008881", class_id=None),
            make_student_payload(name="No Class B", nisn="1000008882", class_id=None),
        ]

        response = client.post("/students/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 2
        assert len(body["failed"]) == 0

        for payload in payloads:
            student = db_session.scalar(select(Student).where(Student.nisn == payload["nisn"]))
            assert student is not None
            assert student.class_id is None


class TestBulkCreateEdgeCases:
    """Failure modes. Some of these mirror your single-POST /students route,
    others are bulk-specific."""

    def test_empty_list_request(self, client):
        """DECISION: empty list -> 200 with empty succeeded/failed (no-op),
        not 422. There's nothing invalid about "import zero rows" from a
        spreadsheet UI perspective (e.g. user selected no rows to submit)."""
        response = client.post("/students/bulk", json=[])

        assert response.status_code == 200
        body = response.json()
        assert body["succeeded"] == []
        assert body["failed"] == []

    def test_duplicate_nisn_against_existing_db_row(self, client, student_factory):
        """One row in the batch has an nisn that already exists in the DB
        (student_factory seeds it first). That row should land in `failed`
        with a useful error, and it must NOT block the other valid rows in
        the same batch from succeeding."""
        student_factory(name="Existing", nisn="1000000001")

        payloads = [
            make_student_payload(name="Valid A", nisn="1000000002"),
            make_student_payload(name="Valid B", nisn="1000000003"),
            make_student_payload(name="Colliding", nisn="1000000001"),
        ]

        response = client.post("/students/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 2
        succeeded_indices = {item["index"] for item in body["succeeded"]}
        assert succeeded_indices == {0, 1}

        assert len(body["failed"]) == 1
        failed_item = body["failed"][0]
        assert failed_item["index"] == 2
        assert failed_item["error"] == "duplicate nisn"

    def test_duplicate_nisn_within_same_batch(self, client):
        """BULK-SPECIFIC CASE: two rows in the SAME request both use nisn
        '1000000099'. Neither exists in the DB beforehand.

        DECISION: Python pre-scans nisns across the batch before touching
        SQLAlchemy. If a nisn appears more than once in the incoming batch,
        BOTH (all) rows using it fail -- not "first wins". This lets the
        user see every offending row and decide which one is correct,
        rather than silently keeping an arbitrary "first" row.

        The error message is "duplicate nisn in batch", distinct from
        "duplicate nisn" (which is reserved for collisions against an
        existing DB row) -- see test_duplicate_nisn_batch_vs_db_have_distinct_errors.
        """
        payloads = [
            make_student_payload(name="Dupe A", nisn="1000000099"),
            make_student_payload(name="Dupe B", nisn="1000000099"),
            make_student_payload(name="Valid", nisn="1000000050"),
        ]

        response = client.post("/students/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 1
        assert body["succeeded"][0]["index"] == 2

        assert len(body["failed"]) == 2
        failed_indices = {item["index"] for item in body["failed"]}
        assert failed_indices == {0, 1}
        for failed_item in body["failed"]:
            assert failed_item["error"] == "duplicate nisn in batch"

    def test_duplicate_nisn_batch_vs_db_have_distinct_errors(self, client, student_factory):
        """EDGE CASE: distinguishes the two different "duplicate nisn"
        scenarios so a frontend can tell a teacher "you typed this twice"
        vs "this student is already in the system".

        Row 0 and row 1 collide with EACH OTHER (in-batch duplicate).
        Row 2 collides with an EXISTING DB row (pre-seeded).
        These must produce different error strings.
        """
        student_factory(name="Already Exists", nisn="1000000001")

        payloads = [
            make_student_payload(name="In-batch Dupe A", nisn="1000000077"),
            make_student_payload(name="In-batch Dupe B", nisn="1000000077"),
            make_student_payload(name="DB Dupe", nisn="1000000001"),
        ]

        response = client.post("/students/bulk", json=payloads)

        assert response.status_code == 422
        body = response.json()

        assert len(body["succeeded"]) == 0
        assert len(body["failed"]) == 3

        failed_by_index = {item["index"]: item for item in body["failed"]}

        assert failed_by_index[0]["error"] == "duplicate nisn in batch"
        assert failed_by_index[1]["error"] == "duplicate nisn in batch"
        assert failed_by_index[2]["error"] == "duplicate nisn"

        # The two error strings must not be interchangeable
        assert failed_by_index[0]["error"] != failed_by_index[2]["error"]

    def test_nonexistent_class_id_in_one_row(self, client, class_factory):
        """One row references a class_id that doesn't exist (e.g. 99999).
        That row fails, other valid rows in the batch still succeed."""
        class_ = class_factory()

        payloads = [
            make_student_payload(name="Valid", nisn="1000000001", class_id=class_.class_id),
            make_student_payload(name="Bad Class", nisn="1000000002", class_id=99999),
        ]

        response = client.post("/students/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 1
        assert body["succeeded"][0]["index"] == 0

        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 1

    def test_missing_required_field(self, client, class_factory):
        """One row is missing `nisn` entirely. Per the agreed contract, this
        route validates rows manually/loosely (not list[StudentRequest]
        with strict Pydantic per-item validation) so ONE malformed row
        lands in `failed` while the rest of the batch still succeeds --
        it must NOT 422 the entire request.
        """
        class_ = class_factory()

        payloads = [
            make_student_payload(name="Valid", nisn="1000000001", class_id=class_.class_id),
            {"name": "Missing NISN", "class_id": class_.class_id, "current": True},  # no "nisn" key
        ]

        response = client.post("/students/bulk", json=payloads)

        # Must NOT be a blanket 422 -- the malformed row is a per-row failure
        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 1
        assert body["succeeded"][0]["index"] == 0

        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 1
        assert "error" in body["failed"][0]

    def test_large_batch_all_valid(self, client, class_factory, db_session):
        """Boundary-ish case: confirm nothing breaks with a bigger batch
        (e.g. 100 rows) -- realistic for a CSV/XLSX import of a whole class
        roster. Mostly a smoke test that nothing is silently truncating
        the list."""
        class_ = class_factory()
        payloads = [
            make_student_payload(name=f"Bulk Student {i}", nisn=f"20000{i:05d}", class_id=class_.class_id)
            for i in range(100)
        ]

        response = client.post("/students/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 100
        assert len(body["failed"]) == 0

        # count = db_session.scalar(
        #     select(Student).where(Student.nisn.like("20000%"))
        # )
        all_created = db_session.scalars(
            select(Student).where(Student.nisn.like("20000%"))
        ).all()
        assert len(all_created) == 100


class TestBulkCreateResponseShape:
    """Assert the CONTRACT itself, not just outcomes -- these tests would
    catch someone accidentally renaming a field or changing the shape."""

    def test_response_has_succeeded_and_failed_keys(self, client, class_factory):
        """Even with a batch that's 100% successful, `failed` should still
        be present as an empty list, not omitted. Same in reverse. (Shape
        of individual items -- {"index","student"} vs {"index","error",
        "student"} -- is asserted in the more targeted shape tests below.)"""
        class_ = class_factory()
        payloads = [make_student_payload(name="Solo", nisn="1000000001", class_id=class_.class_id)]

        response = client.post("/students/bulk", json=payloads)

        assert response.status_code == 200
        body = response.json()
        assert "succeeded" in body
        assert "failed" in body
        assert isinstance(body["succeeded"], list)
        assert isinstance(body["failed"], list)
        assert body["failed"] == []

    def test_failed_item_includes_input_and_error(self, client, student_factory):
        """Assert the shape of an individual `failed` entry: "index",
        "error", and "student" (the original payload sent for that row --
        useful for a spreadsheet UI showing the user exactly which row +
        what they typed)."""
        student_factory(name="Existing", nisn="1000000001")
        bad_payload = make_student_payload(name="Colliding", nisn="1000000001")

        response = client.post("/students/bulk", json=[bad_payload])

        assert response.status_code == 422
        body = response.json()
        assert len(body["failed"]) == 1
        failed_item = body["failed"][0]

        assert failed_item["index"] == 0
        assert isinstance(failed_item["error"], str)
        assert failed_item["error"] != ""
        assert failed_item["student"] == bad_payload

    def test_succeeded_item_matches_studentresponse_shape(self, client, class_factory):
        """Assert a `succeeded` entry is {"index": ..., "student": {...}},
        where "student" carries the same fields as the existing
        StudentResponse (id, name, nisn, current, class_id, ...). The
        student payload is nested rather than merged flat onto the item,
        so success and failure items share a predictable top-level shape
        ("index" + one branch-specific key) without conflating "what was
        sent" with "what the DB now holds"."""
        class_ = class_factory()
        payload = make_student_payload(name="Shaped", nisn="1000000001", class_id=class_.class_id, current=True)

        response = client.post("/students/bulk", json=[payload])

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 1
        item = body["succeeded"][0]

        assert set(item.keys()) == {"index", "student"}
        assert item["index"] == 0

        student = item["student"]
        expected_keys = {"id", "name", "nisn", "current", "class_id"}
        assert expected_keys.issubset(student.keys())
        assert isinstance(student["id"], int)
        assert student["name"] == "Shaped"
        assert student["nisn"] == "1000000001"
        assert student["current"] is True
        assert student["class_id"] == class_.class_id


# ===========================================================================
# 2. BULK UPDATE -- PATCH /students/bulk
# ===========================================================================
class TestBulkUpdate:
    def test_updates_multiple_students(self, client, seeded_students_and_classes, db_session):
        """Happy path: PATCH several existing students' fields (e.g. move
        them to a different class_id) in one request, confirm DB reflects
        the changes."""
        students = seeded_students_and_classes
        target_a, target_b = students[0], students[1]
        new_class_id = students[-1].class_id  # class_index 3 ("10D")

        payload = [
            {
                "id": target_a.id,
                "name": target_a.name,
                "nisn": target_a.nisn,
                "class_id": new_class_id,
                "current": target_a.current,
            },
            {
                "id": target_b.id,
                "name": "Renamed Liz",
                "nisn": target_b.nisn,
                "class_id": new_class_id,
                "current": target_b.current,
            },
        ]

        response = client.patch("/students/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 2
        assert len(body["failed"]) == 0

        db_session.expire_all()
        refreshed_a = db_session.get(Student, target_a.id)
        refreshed_b = db_session.get(Student, target_b.id)
        assert refreshed_a.class_id == new_class_id
        assert refreshed_b.class_id == new_class_id
        assert refreshed_b.name == "Renamed Liz"

    def test_mass_reassign_class(self, client, seeded_students_and_classes, db_session):
        """Mass-moving a group of students to a new class_id in one request
        -- flagged earlier as a specific risk case, worth its own explicit
        test."""
        students = seeded_students_and_classes
        class_a_students = [s for s in students if s.name in ("Shaun", "Ed", "Liz", "David")]
        new_class_id = students[-1].class_id

        payload = [
            {
                "id": s.id,
                "name": s.name,
                "nisn": s.nisn,
                "class_id": new_class_id,
                "current": s.current,
            }
            for s in class_a_students
        ]

        response = client.patch("/students/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == len(class_a_students)
        assert len(body["failed"]) == 0

        db_session.expire_all()
        for s in class_a_students:
            refreshed = db_session.get(Student, s.id)
            assert refreshed.class_id == new_class_id

        # Students NOT in the batch must be untouched
        untouched = [s for s in students if s not in class_a_students]
        for s in untouched:
            refreshed = db_session.get(Student, s.id)
            assert refreshed.class_id == s.class_id


class TestBulkUpdateEdgeCases:
    def test_one_id_does_not_exist(self, client, seeded_students_and_classes):
        """One row's id isn't in the DB. That row fails, others succeed."""
        students = seeded_students_and_classes
        real_student = students[0]

        payload = [
            {
                "id": real_student.id,
                "name": real_student.name,
                "nisn": real_student.nisn,
                "class_id": real_student.class_id,
                "current": real_student.current,
            },
            {
                "id": 999999,
                "name": "Ghost",
                "nisn": "1000009999",
                "class_id": None,
                "current": True,
            },
        ]

        response = client.patch("/students/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()

        assert len(body["succeeded"]) == 1
        assert body["succeeded"][0]["index"] == 0

        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 1

    def test_update_creates_nisn_collision_with_another_row_in_db(self, client, seeded_students_and_classes):
        """Row A is updated to use an nisn that belongs to a DIFFERENT
        existing student (not itself). Should fail per-row, same 409 logic
        as the single PUT route."""
        students = seeded_students_and_classes
        student_a, student_b = students[0], students[1]

        payload = [
            {
                "id": student_a.id,
                "name": student_a.name,
                "nisn": student_b.nisn,  # collides with student_b's current nisn
                "class_id": student_a.class_id,
                "current": student_a.current,
            },
        ]

        response = client.patch("/students/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 0
        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 0
        assert "nisn" in body["failed"][0]["error"].lower()

    def test_two_rows_in_batch_try_to_swap_nisns(self, client, seeded_students_and_classes, db_session):
        """Student X currently has nisn 'A', student Y has nisn 'B'. Batch
        says: set X's nisn to 'B', set Y's nisn to 'A'.

        DECISION: out of scope for v1. Processed row-by-row, updating X to
        Y's CURRENT nisn will collide (Y hasn't been updated away from it
        yet), so this is documented as a per-row failure -- NOT a supported
        atomic swap. Both rows are expected to fail with a duplicate-nisn
        style error, even though the end state (if computed as a set)
        would have been valid. If a future version wants to support true
        swaps, this test should be updated to reflect a two-pass diffing
        strategy instead.
        """
        students = seeded_students_and_classes
        student_x, student_y = students[0], students[1]
        original_x_nisn = student_x.nisn
        original_y_nisn = student_y.nisn

        payload = [
            {
                "id": student_x.id,
                "name": student_x.name,
                "nisn": original_y_nisn,
                "class_id": student_x.class_id,
                "current": student_x.current,
            },
            {
                "id": student_y.id,
                "name": student_y.name,
                "nisn": original_x_nisn,
                "class_id": student_y.class_id,
                "current": student_y.current,
            },
        ]

        response = client.patch("/students/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()

        # Documented v1 behavior: swap is not supported, at least one (or
        # both) rows fail rather than silently succeeding in an
        # order-dependent way.
        assert len(body["failed"]) >= 1

        db_session.expire_all()
        refreshed_x = db_session.get(Student, student_x.id)
        refreshed_y = db_session.get(Student, student_y.id)
        # Nisns must remain globally unique regardless of outcome
        assert refreshed_x.nisn != refreshed_y.nisn

    def test_nonexistent_class_id_in_one_row(self, client, seeded_students_and_classes):
        """Mirrors the create case: a row referencing a non-existent
        class_id fails without blocking sibling rows."""
        students = seeded_students_and_classes
        real_student = students[0]

        payload = [
            {
                "id": real_student.id,
                "name": real_student.name,
                "nisn": real_student.nisn,
                "class_id": 99999,
                "current": real_student.current,
            },
        ]

        response = client.patch("/students/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body["succeeded"]) == 0
        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 0


class TestBulkUpdateResponseShape:
    def test_response_shape_matches_bulk_create_contract(self, client, seeded_students_and_classes):
        """The create and update bulk responses use the SAME shape
        (succeeded/failed with index) -- a frontend built against one
        should work against the other without special-casing."""
        students = seeded_students_and_classes
        real_student = students[0]

        payload = [
            {
                "id": real_student.id,
                "name": real_student.name,
                "nisn": real_student.nisn,
                "class_id": real_student.class_id,
                "current": real_student.current,
            },
            {
                "id": 999999,
                "name": "Ghost",
                "nisn": "1000009998",
                "class_id": None,
                "current": True,
            },
        ]

        response = client.patch("/students/bulk", json=payload)

        assert response.status_code == 200
        body = response.json()

        assert set(body.keys()) == {"succeeded", "failed"}
        assert isinstance(body["succeeded"], list)
        assert isinstance(body["failed"], list)

        assert set(body["succeeded"][0].keys()) == {"index", "student"}
        assert "id" in body["succeeded"][0]["student"]

        assert "index" in body["failed"][0]
        assert "error" in body["failed"][0]
        assert "student" in body["failed"][0]


# ===========================================================================
# 3. BULK DELETE -- POST /students/bulk-delete
# ===========================================================================
# Contract: pre-check all ids exist. If ANY are missing, delete NOTHING and
# return 404 with every missing id. Only if all ids are valid do you delete
# all of them, returning 204. Duplicate ids in the request are deduped
# before the existence check.
class TestBulkDelete:
    def test_deletes_multiple_existing_students(self, client, seeded_students_and_classes, db_session):
        """Happy path: delete 3 existing students in one call."""
        students = seeded_students_and_classes
        to_delete = students[:3]
        to_keep = students[3:]
        delete_ids = [s.id for s in to_delete]

        response = client.post("/students/bulk-delete", json={"ids": delete_ids})

        assert response.status_code == 204
        assert response.content == b""

        for s in to_delete:
            assert db_session.get(Student, s.id) is None

        # The test most people forget: confirm untargeted rows survive
        for s in to_keep:
            assert db_session.get(Student, s.id) is not None

    def test_deleting_student_with_null_class_id_works(self, client, student_factory, db_session):
        """A student with no class assigned deletes fine, no FK weirdness."""
        student = student_factory(name="No Class", nisn="1000000001", class_id=None)

        response = client.post("/students/bulk-delete", json={"ids": [student.id]})

        assert response.status_code == 204
        assert db_session.get(Student, student.id) is None


class TestBulkDeleteEdgeCases:
    def test_one_id_does_not_exist_blocks_entire_batch(self, client, seeded_students_and_classes, db_session):
        """Per the agreed contract: if even one id is invalid, NOTHING
        should be deleted -- not even the valid ones."""
        students = seeded_students_and_classes
        real_ids = [students[0].id, students[1].id]
        fake_id = 999999

        response = client.post("/students/bulk-delete", json={"ids": real_ids + [fake_id]})

        assert response.status_code == 404

        # Proof of "all or nothing": the valid students must STILL be there
        for student_id in real_ids:
            assert db_session.get(Student, student_id) is not None

    def test_multiple_missing_ids_all_reported_at_once(self, client, seeded_students_and_classes):
        """Report ALL bad ids, not just the first one hit."""
        students = seeded_students_and_classes
        real_id = students[0].id
        fake_ids = [888888, 999999]

        response = client.post("/students/bulk-delete", json={"ids": [real_id] + fake_ids})

        assert response.status_code == 404
        body = response.json()
        assert set(body["missing_ids"]) == set(fake_ids)

    def test_empty_id_list(self, client, db_session):
        """DECISION: empty id list -> 204, no-op, nothing deleted. Matches
        the "nothing to do" treatment given to empty bulk-create lists."""
        # existing_count_before = db_session.scalar(
        #     select(Student.id)
        # )

        response = client.post("/students/bulk-delete", json={"ids": []})

        assert response.status_code == 204
        assert response.content == b""

    def test_duplicate_ids_in_same_request(self, client, seeded_students_and_classes, db_session):
        """DECISION: duplicate ids are deduped before the existence
        pre-check -- [id, id, other_id] behaves identically to
        [id, other_id]. The student is deleted once; the duplicate entry
        is not treated as an error and does not (incorrectly) cause a
        "missing" report on the second pass after the first delete."""
        students = seeded_students_and_classes
        target = students[0]

        response = client.post(
            "/students/bulk-delete", json={"ids": [target.id, target.id, students[1].id]}
        )

        assert response.status_code == 204
        assert db_session.get(Student, target.id) is None
        assert db_session.get(Student, students[1].id) is None


class TestBulkDeleteResponseShape:
    def test_success_response_is_empty_204(self, client, seeded_students_and_classes):
        """Matches the single-delete convention (204, no body) -- bulk
        delete stays consistent with that rather than inventing a
        different success shape just because it's plural."""
        students = seeded_students_and_classes
        ids = [s.id for s in students[:2]]

        response = client.post("/students/bulk-delete", json={"ids": ids})

        assert response.status_code == 204
        assert response.content == b""

    def test_failure_response_shape(self, client, seeded_students_and_classes):
        """Pin down the 404 body shape: {"missing_ids": [...]}. The
        frontend needs the exact key name to build the per-row error UI."""
        students = seeded_students_and_classes
        real_id = students[0].id
        fake_id = 999999

        response = client.post("/students/bulk-delete", json={"ids": [real_id, fake_id]})

        assert response.status_code == 404
        body = response.json()
        assert set(body.keys()) == {"missing_ids"}
        assert isinstance(body["missing_ids"], list)
        assert fake_id in body["missing_ids"]
