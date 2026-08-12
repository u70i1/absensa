from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.models.scan_log import ScanLog
from app.models.student import Student
from sqlalchemy import select

# match whatever your app reads from the TZ env var — don't hardcode
# a different literal here than what your app actually uses
LOCAL_TZ = ZoneInfo(settings.timezone)
from zoneinfo import ZoneInfo


def make_scan(db_session, student, when: datetime):
    """
    Helper: insert a scan log with an EXPLICIT timestamp.
    """
    class_name = student.class_.class_name if student.class_ is not None else None

    log = ScanLog(
        student_nisn=student.nisn,
        name=student.name,
        class_name=class_name,
        timestamp=when,
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


@pytest.fixture
def existing_class(class_factory):
    """A default class (11B) for most tests."""
    return class_factory(class_name="11B")


@pytest.fixture
def existing_student(student_factory, existing_class):
    """A single active, scannable student — the default case most tests need."""
    return student_factory(
        name="Nicholas Angle",
        nisn="1234567890",
        class_id=existing_class.class_id,
        current=True,
    )


def scan_logs_for(db_session, nisn):
    stmt = select(ScanLog).filter_by(student_nisn=nisn)
    return db_session.scalars(stmt).all()


class TestGetScan:
    # ---------------------------------------------------------------------------
    # Basic shape / empty state
    # ---------------------------------------------------------------------------

    def test_get_scan_empty_returns_empty_list(self, client):
        """No scans at all -> 200 with a bare empty list, not 404."""
        response = client.get("/scans")

        assert response.status_code == 200, "Empty result set should still be 200"
        assert response.json() == [], "Should return a bare empty list"

    def test_get_scan_returns_bare_list_not_wrapped(
        self, client, student_factory, db_session
    ):
        """Response body should be a raw list, not {"items": [...]} or similar."""
        student = student_factory()
        make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.get("/scans")
        body = response.json()

        assert isinstance(body, list), (
            "Body should be a bare list, not an object wrapper"
        )
        assert len(body) == 1

    # ---------------------------------------------------------------------------
    # Ordering (recency) — this underpins every pagination test below.
    # If your endpoint doesn't .order_by(ScanLog.timestamp.desc()), these fail.
    # ---------------------------------------------------------------------------

    def test_get_scan_orders_by_recency_desc(self, client, student_factory, db_session):
        student = student_factory()
        now = datetime.now(LOCAL_TZ)

        oldest = make_scan(db_session, student, now - timedelta(days=2))
        middle = make_scan(db_session, student, now - timedelta(days=1))
        newest = make_scan(db_session, student, now)

        response = client.get("/scans")
        body = response.json()

        ids_in_order = [row["scan_id"] for row in body]
        assert ids_in_order == [newest.scan_id, middle.scan_id, oldest.scan_id], (
            "Expected newest-first ordering"
        )

    # ---------------------------------------------------------------------------
    # Pagination
    # ---------------------------------------------------------------------------

    def test_get_scan_default_limit_is_30(self, client, student_factory, db_session):
        """Insert 35 scans, hit /scans with no query params, expect exactly 30 back."""
        student = student_factory()
        now = datetime.now(LOCAL_TZ)

        for i in range(35):
            make_scan(db_session, student, now - timedelta(minutes=i))

        response = client.get("/scans")
        body = response.json()

        assert response.status_code == 200
        assert len(body) == 30, "Default limit should be 30"

    def test_get_scan_respects_custom_limit(self, student_factory, client, db_session):
        student = student_factory()
        now = datetime.now(LOCAL_TZ)
        for i in range(10):
            make_scan(db_session, student, now - timedelta(minutes=i))

        response = client.get("/scans", params={"limit": 5})
        body = response.json()

        assert len(body) == 5

    def test_get_scan_page_2_returns_next_slice(
        self, student_factory, client, db_session
    ):
        """
        With limit=5 and 12 rows, page=2 should return rows 6-10 (i.e. the
        6th-newest through 10th-newest), not overlap page 1 and not restart.
        """
        student = student_factory()
        now = datetime.now(LOCAL_TZ)
        logs = [
            make_scan(db_session, student, now - timedelta(minutes=i))
            for i in range(12)
        ]
        # logs[0] is newest (smallest offset), logs[11] is oldest

        page_1 = client.get("/scans", params={"limit": 5, "page": 1}).json()
        page_2 = client.get("/scans", params={"limit": 5, "page": 2}).json()

        page_1_ids = [row["scan_id"] for row in page_1]
        page_2_ids = [row["scan_id"] for row in page_2]

        assert page_1_ids == [logs[i].scan_id for i in range(0, 5)]
        assert page_2_ids == [logs[i].scan_id for i in range(5, 10)]
        assert set(page_1_ids).isdisjoint(page_2_ids), "Pages should not overlap"

    def test_get_scan_page_beyond_last_page_returns_empty_list(
        self, student_factory, client, db_session
    ):
        """Requesting a page past the available data -> empty list, still 200."""
        student = student_factory()
        make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.get("/scans", params={"limit": 30, "page": 999})

        assert response.status_code == 200
        assert response.json() == []

    def test_get_scan_limit_zero_is_422(self, client):
        response = client.get("/scans", params={"limit": 0})
        assert response.status_code == 422

    def test_get_scan_negative_limit_is_422(self, client):
        response = client.get("/scans", params={"limit": -5})
        assert response.status_code == 422

    def test_get_scan_negative_page_is_422(self, client):
        response = client.get("/scans", params={"page": -1})
        assert response.status_code == 422

    def test_get_scan_page_zero_is_422(self, client):
        """page is 1-indexed per the spec (default 1) — 0 is out of range, not 'first page'."""
        response = client.get("/scans", params={"page": 0})
        assert response.status_code == 422

    # ---------------------------------------------------------------------------
    # NISN filter
    # ---------------------------------------------------------------------------

    def test_get_scan_filters_by_nisn(
        self, client, student_factory, class_factory, db_session
    ):
        class_a = class_factory(class_name="11A")
        class_b = class_factory(class_name="11B")

        student_a = student_factory(
            nisn="1111111111", class_id=class_a.class_id, name="Student A"
        )
        student_b = student_factory(
            nisn="2222222222", class_id=class_b.class_id, name="Student B"
        )
        now = datetime.now(LOCAL_TZ)

        make_scan(db_session, student_a, now)
        make_scan(db_session, student_b, now)

        response = client.get("/scans", params={"nisn": "1111111111"})
        body = response.json()

        assert len(body) == 1
        assert body[0]["student_nisn"] == "1111111111"

    def test_get_scan_filter_nisn_no_matches_returns_empty_list(
        self, student_factory, client, db_session
    ):
        """Filtering by a NISN that has no scans -> empty list, not 404."""
        student = student_factory(nisn="1111111111")
        make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.get("/scans", params={"nisn": "9999999999"})

        assert response.status_code == 200
        assert response.json() == []

    # ---------------------------------------------------------------------------
    # Date range filter
    #
    # Naive YYYY-MM-DD dates. The endpoint must decide how date_to is
    # interpreted — see the boundary test below, it's the one that actually
    # pins down "inclusive of the whole day" behavior.
    # ---------------------------------------------------------------------------

    def test_get_scan_filters_by_date_range(self, student_factory, client, db_session):
        student = student_factory()

        inside_range = make_scan(
            db_session, student, datetime(2026, 7, 15, 12, 0, tzinfo=LOCAL_TZ)
        )

        response = client.get(
            "/scans", params={"date_from": "2026-07-10", "date_to": "2026-07-20"}
        )
        body = response.json()
        ids = [row["scan_id"] for row in body]

        assert ids == [inside_range.scan_id], (
            "Only the scan inside the range should be returned"
        )

    def test_get_scan_date_to_is_inclusive_of_entire_day(
        self, student_factory, client, db_session
    ):
        """
        The boundary case: a scan at 23:30 on date_to's day must be INCLUDED.

        If the endpoint naively does `timestamp <= date_to`, Postgres reads
        date_to as midnight (00:00:00) of that day, and this scan — which
        happened later the same day — gets wrongly excluded. This test fails
        if that off-by-one is present.
        """
        student = student_factory()
        late_in_day = make_scan(
            db_session, student, datetime(2026, 8, 4, 23, 30, tzinfo=LOCAL_TZ)
        )

        response = client.get(
            "/scans", params={"date_from": "2026-08-01", "date_to": "2026-08-04"}
        )
        body = response.json()
        ids = [row["scan_id"] for row in body]

        assert late_in_day.scan_id in ids, (
            "date_to=2026-08-04 should include scans up through 23:59:59 that day"
        )

    def test_get_scan_date_from_only(self, student_factory, client, db_session):
        """date_from with no date_to should return everything from that date onward."""
        student = student_factory()

        older = make_scan(
            db_session, student, datetime(2026, 1, 1, 12, 0, tzinfo=LOCAL_TZ)
        )
        newer = make_scan(
            db_session, student, datetime(2026, 7, 1, 12, 0, tzinfo=LOCAL_TZ)
        )

        response = client.get("/scans", params={"date_from": "2026-06-01"})
        ids = [row["scan_id"] for row in response.json()]

        assert newer.scan_id in ids
        assert older.scan_id not in ids

    def test_get_scan_date_to_only(self, student_factory, client, db_session):
        """date_to with no date_from should return everything up through that date."""
        student = student_factory()

        older = make_scan(
            db_session, student, datetime(2026, 1, 1, 12, 0, tzinfo=LOCAL_TZ)
        )
        newer = make_scan(
            db_session, student, datetime(2026, 7, 1, 12, 0, tzinfo=LOCAL_TZ)
        )

        response = client.get("/scans", params={"date_to": "2026-03-01"})
        ids = [row["scan_id"] for row in response.json()]

        assert older.scan_id in ids
        assert newer.scan_id not in ids

    def test_get_scan_date_from_after_date_to_is_422(self, client):
        response = client.get(
            "/scans", params={"date_from": "2026-08-04", "date_to": "2026-08-01"}
        )
        assert response.status_code == 422

    def test_get_scan_malformed_date_is_422(self, client):
        response = client.get("/scans", params={"date_from": "not-a-date"})
        assert response.status_code == 422

    def test_get_scan_wrong_date_format_is_422(self, client):
        """DD-MM-YYYY or similar should be rejected — spec is strictly YYYY-MM-DD."""
        response = client.get("/scans", params={"date_from": "04-08-2026"})
        assert response.status_code == 422

    # ---------------------------------------------------------------------------
    # Scan lookup by id
    # ---------------------------------------------------------------------------

    def test_get_scan_by_id_returns_matching_scan(
        self, student_factory, client, db_session
    ):
        student = student_factory()
        target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.get(f"/scans/{target.scan_id}")
        body = response.json()

        assert response.status_code == 200
        assert body["scan_id"] == target.scan_id
        assert body["student_nisn"] == student.nisn

    def test_get_scan_by_id_returns_bare_object_not_list(
        self, student_factory, client, db_session
    ):
        """Single-item lookup should return a JSON object, not a one-item list."""
        student = student_factory()
        target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.get(f"/scans/{target.scan_id}")
        body = response.json()

        assert isinstance(body, dict), "Single scan lookup should return a bare object"

    def test_get_scan_by_id_missing_returns_404(
        self, student_factory, client, db_session
    ):
        """A scan_id that doesn't exist should 404, same convention as POST /scans
        for a missing student."""
        # make sure the table isn't empty, so a passing test isn't just an
        # accidental "nothing exists yet" false positive
        student = student_factory()
        make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.get("/scans/999999")

        assert response.status_code == 404

    def test_get_scan_by_id_non_integer_is_422(self, client):
        """FastAPI path param typed as int should reject non-numeric ids at the
        validation layer, before your route logic even runs."""
        response = client.get("/scans/not-an-id")

        assert response.status_code == 422

    # ---------------------------------------------------------------------------
    # Combined filters
    # ---------------------------------------------------------------------------

    def test_get_scan_combines_nisn_and_date_range(
        self, client, db_session, class_factory, student_factory
    ):

        class_a = class_factory(class_name="11A")
        class_b = class_factory(class_name="11B")

        student_a = student_factory(
            nisn="1111111111", class_id=class_a.class_id, name="Student A"
        )
        student_b = student_factory(
            nisn="2222222222", class_id=class_b.class_id, name="Student B"
        )

        target = make_scan(
            db_session, student_a, datetime(2026, 7, 15, 12, 0, tzinfo=LOCAL_TZ)
        )
        # same student, wrong date
        make_scan(db_session, student_a, datetime(2026, 1, 1, 12, 0, tzinfo=LOCAL_TZ))
        # right date, wrong student
        make_scan(db_session, student_b, datetime(2026, 7, 15, 12, 0, tzinfo=LOCAL_TZ))

        response = client.get(
            "/scans",
            params={
                "nisn": "1111111111",
                "date_from": "2026-07-01",
                "date_to": "2026-07-31",
            },
        )
        ids = [row["scan_id"] for row in response.json()]

        assert ids == [target.scan_id]

    # ---------------------------------------------------------------------------
    # Scan for a student with no class assigned (nullable class_id)
    #
    # make_scan() already handles student.class_ is None by writing
    # ScanLog.class_ = None — this pins that behavior down explicitly rather
    # than leaving it as an implicit side effect of the helper.
    # ---------------------------------------------------------------------------

    def test_get_scan_for_student_without_class_has_null_class(
        self, client, db_session
    ):
        student = Student(name="No Class Yet", class_id=None, nisn="5555555555")
        db_session.add(student)
        db_session.commit()
        db_session.refresh(student)

        target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.get(f"/scans/{target.scan_id}")
        body = response.json()

        assert response.status_code == 200
        assert body["class_name"] is None


class TestPostScan:
    def test_scan_creates_log(self, client, db_session, existing_student):
        """Scanning an existing student should log it correctly to scan_logs."""
        response = client.post("/scans", json={"nisn": existing_student.nisn})

        assert response.status_code == 200, "Status code should be 200"
        body = response.json()
        assert body["name"] == existing_student.name, "Name is wrong"

        logs = scan_logs_for(db_session, existing_student.nisn)
        assert len(logs) == 1, "Unexpected amount of logs"

    def test_scan_log_reflects_current_class(
        self, client, db_session, existing_student, existing_class
    ):
        """The logged class_ should be a snapshot of the student's class name
        at scan time"""
        response = client.post("/scans", json={"nisn": existing_student.nisn})

        assert response.status_code == 200
        assert response.json()["class_name"] == existing_class.class_name

        logs = scan_logs_for(db_session, existing_student.nisn)
        assert logs[0].class_name == existing_class.class_name

    def test_scan_missing_returns_404(self, client):
        """Scanning a non-existing NISN should fail clearly."""
        response = client.post("/scans", json={"nisn": "0000000000"})

        assert response.status_code == 404, "Response status should be 404"

    # ---------------------------------------------------------------------------
    # Duplicate-scan (same local day) logic
    # ---------------------------------------------------------------------------

    def test_scan_same_day_duplicate_returns_409(
        self, client, db_session, existing_student
    ):
        """Scanning the same student twice on the same day should conflict."""
        first_scan = client.post("/scans", json={"nisn": existing_student.nisn})
        second_scan = client.post("/scans", json={"nisn": existing_student.nisn})

        assert first_scan.status_code == 200, "First scan status code should be 200"
        assert second_scan.status_code == 409, (
            "Duplicate scan status code should be 409"
        )

        logs = scan_logs_for(db_session, existing_student.nisn)
        assert len(logs) == 1, "Duplicate scan should not be added in the database"

    def test_scan_next_local_day_is_not_a_duplicate(
        self, client, db_session, existing_student
    ):
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
        self, client, db_session, existing_student
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
        self, client, db_session, existing_student
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

    def test_scan_inactive_student_returns_404(self, client, student_factory):
        """
        A student who exists but is marked current=False (e.g. graduated/transferred)
        should be treated as not-scannable -- same as not existing at all.
        Only relevant if your endpoint actually filters on `current`; if it doesn't,
        this test will tell you that's a gap, not a false failure.
        """
        inactive = student_factory(
            name="Old Alumni",
            nisn="9999999999",
            class_id=None,  # class not required for this test
            current=False,
        )

        response = client.post("/scans", json={"nisn": inactive.nisn})

        assert response.status_code == 404, (
            "Inactive/non-current students shouldn't scan in"
        )

    def test_scan_student_without_class_still_scannable(self, client, student_factory):
        """
        class_id is nullable -- a student with no class assigned yet must
        still be able to scan in. The logged class_ should come back as None,
        not crash the endpoint or silently invent a value.
        """
        unassigned = student_factory(
            name="Unassigned Kid",
            nisn="4445556667",
            class_id=None,
            current=True,
        )

        response = client.post("/scans", json={"nisn": unassigned.nisn})

        assert response.status_code == 200
        assert response.json()["class_name"] is None

    # ---------------------------------------------------------------------------
    # Request validation
    # ---------------------------------------------------------------------------

    def test_scan_missing_nisn_returns_422(self, client):
        """Missing 'nisn' field should fail request validation, not fall
        through to 404 logic."""
        response = client.post("/scans", json={})
        assert response.status_code == 422, "Missing nisn should be a validation error"

    def test_scan_integer_nisn_is_coerced_and_succeeds(self, client, existing_student):
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

    def test_scan_wrong_type_nisn_returns_422(self, client):
        """A type Pydantic can't coerce to str (e.g. a list) should still 422."""
        response = client.post("/scans", json={"nisn": ["not", "a", "string"]})
        assert response.status_code == 422


class TestDeleteScan:
    def test_delete_scan_removes_row(
        self, client, db_session, class_factory, student_factory
    ):
        """Deleting an existing scan should actually remove it from the DB —
        not just return a nice status code."""
        class_ = class_factory(class_name="11B")
        student = student_factory(
            name="Nicholas Angle", nisn="1234567890", class_id=class_.class_id
        )
        target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.delete(f"/scans/{target.scan_id}")

        assert response.status_code == 204, "Successful delete should be 204"
        assert response.content == b"", "204 response should have an empty body"

        # the real assertion: is it actually gone from the DB, not just "did
        # the endpoint say 204". Query directly rather than trusting the response.
        remaining = db_session.query(ScanLog).filter_by(scan_id=target.scan_id).first()
        assert remaining is None, "Scan should no longer exist in the DB"

    def test_delete_scan_only_removes_the_targeted_row(
        self, client, db_session, class_factory, student_factory
    ):
        """Sanity check against an overly broad DELETE (e.g. missing a WHERE
        clause, or filtering on the wrong column) — make sure siblings survive."""
        class_ = class_factory(class_name="11B")
        student = student_factory(
            name="Nicholas Angle", nisn="1234567890", class_id=class_.class_id
        )
        target = make_scan(db_session, student, datetime.now(LOCAL_TZ))
        survivor = make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.delete(f"/scans/{target.scan_id}")

        assert response.status_code == 204
        still_there = (
            db_session.query(ScanLog).filter_by(scan_id=survivor.scan_id).first()
        )
        assert still_there is not None, "Unrelated scan should not have been deleted"

    def test_delete_scan_missing_returns_404(
        self, client, db_session, class_factory, student_factory
    ):
        """Deleting a scan_id that doesn't exist should 404, consistent with
        GET /scans/{id}'s behavior for a missing id."""
        # seed something unrelated so a passing test isn't just "table is empty"
        class_ = class_factory(class_name="11B")
        student = student_factory(
            name="Nicholas Angle", nisn="1234567890", class_id=class_.class_id
        )
        make_scan(db_session, student, datetime.now(LOCAL_TZ))

        response = client.delete("/scans/999999")

        assert response.status_code == 404

    def test_delete_scan_non_integer_id_is_422(self, client):
        """scan_id typed as int on the path should reject non-numeric input
        at the validation layer, before route logic runs."""
        response = client.delete("/scans/not-an-id")

        assert response.status_code == 422

    def test_delete_scan_is_idempotent_failure_on_second_call(
        self, client, db_session, class_factory, student_factory
    ):
        """Deleting the same id twice: first call succeeds, second call 404s —
        it shouldn't silently 204 again on an already-gone row."""
        class_ = class_factory(class_name="11B")
        student = student_factory(
            name="Nicholas Angle", nisn="1234567890", class_id=class_.class_id
        )
        target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

        first = client.delete(f"/scans/{target.scan_id}")
        second = client.delete(f"/scans/{target.scan_id}")

        assert first.status_code == 204
        assert second.status_code == 404
