from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.scan_log import ScanLog
from app.models.student import Student

# match whatever your app reads from the TZ env var — don't hardcode
# a different literal here than what your app actually uses
LOCAL_TZ = ZoneInfo(settings.timezone)


def make_student(db_session, nisn="1234567890", name="Nicholas Angle", class_="11B"):
    """Helper: insert a student, return it. Reused across most tests here."""
    student = Student(name=name, class_=class_, nisn=nisn, current=True)
    db_session.add(student)
    db_session.commit()
    return student


def make_scan(db_session, student, when: datetime):
    """
    Helper: insert a scan log with an EXPLICIT timestamp.

    We can't rely on server_default=func.now() for range-filter tests —
    we need full control over "when" each row happened, otherwise there's
    no way to assert the boundary behavior deterministically.
    """
    log = ScanLog(
        student_nisn=student.nisn,
        name=student.name,
        class_=student.class_,
        timestamp=when,
    )
    db_session.add(log)
    db_session.commit()
    return log


# ---------------------------------------------------------------------------
# Basic shape / empty state
# ---------------------------------------------------------------------------


def test_get_scan_empty_returns_empty_list(client):
    """No scans at all -> 200 with a bare empty list, not 404."""
    response = client.get("/scans")

    assert response.status_code == 200, "Empty result set should still be 200"
    assert response.json() == [], "Should return a bare empty list"


def test_get_scan_returns_bare_list_not_wrapped(client, db_session):
    """Response body should be a raw list, not {"items": [...]} or similar."""
    student = make_student(db_session)
    make_scan(db_session, student, datetime.now(LOCAL_TZ))

    response = client.get("/scans")
    body = response.json()

    assert isinstance(body, list), "Body should be a bare list, not an object wrapper"
    assert len(body) == 1


# ---------------------------------------------------------------------------
# Ordering (recency) — this underpins every pagination test below.
# If your endpoint doesn't .order_by(ScanLog.timestamp.desc()), these fail.
# ---------------------------------------------------------------------------


def test_get_scan_orders_by_recency_desc(client, db_session):
    student = make_student(db_session)
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


def test_get_scan_default_limit_is_30(client, db_session):
    """Insert 35 scans, hit /scans with no query params, expect exactly 30 back."""
    student = make_student(db_session)
    now = datetime.now(LOCAL_TZ)

    for i in range(35):
        make_scan(db_session, student, now - timedelta(minutes=i))

    response = client.get("/scans")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 30, "Default limit should be 30"


def test_get_scan_respects_custom_limit(client, db_session):
    student = make_student(db_session)
    now = datetime.now(LOCAL_TZ)
    for i in range(10):
        make_scan(db_session, student, now - timedelta(minutes=i))

    response = client.get("/scans", params={"limit": 5})
    body = response.json()

    assert len(body) == 5


def test_get_scan_page_2_returns_next_slice(client, db_session):
    """
    With limit=5 and 12 rows, page=2 should return rows 6-10 (i.e. the
    6th-newest through 10th-newest), not overlap page 1 and not restart.
    """
    student = make_student(db_session)
    now = datetime.now(LOCAL_TZ)
    logs = [
        make_scan(db_session, student, now - timedelta(minutes=i)) for i in range(12)
    ]
    # logs[0] is newest (smallest offset), logs[11] is oldest

    page_1 = client.get("/scans", params={"limit": 5, "page": 1}).json()
    page_2 = client.get("/scans", params={"limit": 5, "page": 2}).json()

    page_1_ids = [row["scan_id"] for row in page_1]
    page_2_ids = [row["scan_id"] for row in page_2]

    assert page_1_ids == [logs[i].scan_id for i in range(0, 5)]
    assert page_2_ids == [logs[i].scan_id for i in range(5, 10)]
    assert set(page_1_ids).isdisjoint(page_2_ids), "Pages should not overlap"


def test_get_scan_page_beyond_last_page_returns_empty_list(client, db_session):
    """Requesting a page past the available data -> empty list, still 200."""
    student = make_student(db_session)
    make_scan(db_session, student, datetime.now(LOCAL_TZ))

    response = client.get("/scans", params={"limit": 30, "page": 999})

    assert response.status_code == 200
    assert response.json() == []


def test_get_scan_limit_zero_is_422(client):
    response = client.get("/scans", params={"limit": 0})
    assert response.status_code == 422


def test_get_scan_negative_limit_is_422(client):
    response = client.get("/scans", params={"limit": -5})
    assert response.status_code == 422


def test_get_scan_negative_page_is_422(client):
    response = client.get("/scans", params={"page": -1})
    assert response.status_code == 422


def test_get_scan_page_zero_is_422(client):
    """page is 1-indexed per the spec (default 1) — 0 is out of range, not 'first page'."""
    response = client.get("/scans", params={"page": 0})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# NISN filter
# ---------------------------------------------------------------------------


def test_get_scan_filters_by_nisn(client, db_session):
    student_a = make_student(db_session, nisn="1111111111", name="Student A")
    student_b = make_student(db_session, nisn="2222222222", name="Student B")
    now = datetime.now(LOCAL_TZ)

    make_scan(db_session, student_a, now)
    make_scan(db_session, student_b, now)

    response = client.get("/scans", params={"nisn": "1111111111"})
    body = response.json()

    assert len(body) == 1
    assert body[0]["student_nisn"] == "1111111111"


def test_get_scan_filter_nisn_no_matches_returns_empty_list(client, db_session):
    """Filtering by a NISN that has no scans -> empty list, not 404."""
    student = make_student(db_session, nisn="1111111111")
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


def test_get_scan_filters_by_date_range(client, db_session):
    student = make_student(db_session)

    before_range = make_scan(
        db_session, student, datetime(2026, 7, 1, 12, 0, tzinfo=LOCAL_TZ)
    )
    inside_range = make_scan(
        db_session, student, datetime(2026, 7, 15, 12, 0, tzinfo=LOCAL_TZ)
    )
    after_range = make_scan(
        db_session, student, datetime(2026, 8, 1, 12, 0, tzinfo=LOCAL_TZ)
    )

    response = client.get(
        "/scans", params={"date_from": "2026-07-10", "date_to": "2026-07-20"}
    )
    body = response.json()
    ids = [row["scan_id"] for row in body]

    assert ids == [inside_range.scan_id], (
        "Only the scan inside the range should be returned"
    )


def test_get_scan_date_to_is_inclusive_of_entire_day(client, db_session):
    """
    The boundary case: a scan at 23:30 on date_to's day must be INCLUDED.

    If the endpoint naively does `timestamp <= date_to`, Postgres reads
    date_to as midnight (00:00:00) of that day, and this scan — which
    happened later the same day — gets wrongly excluded. This test fails
    if that off-by-one is present.
    """
    student = make_student(db_session)
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


def test_get_scan_date_from_only(client, db_session):
    """date_from with no date_to should return everything from that date onward."""
    student = make_student(db_session)

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


def test_get_scan_date_to_only(client, db_session):
    """date_to with no date_from should return everything up through that date."""
    student = make_student(db_session)

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


def test_get_scan_date_from_after_date_to_is_422(client):
    response = client.get(
        "/scans", params={"date_from": "2026-08-04", "date_to": "2026-08-01"}
    )
    assert response.status_code == 422


def test_get_scan_malformed_date_is_422(client):
    response = client.get("/scans", params={"date_from": "not-a-date"})
    assert response.status_code == 422


def test_get_scan_wrong_date_format_is_422(client):
    """DD-MM-YYYY or similar should be rejected — spec is strictly YYYY-MM-DD."""
    response = client.get("/scans", params={"date_from": "04-08-2026"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------


def test_get_scan_by_id_returns_matching_scan(client, db_session):
    student = make_student(db_session)
    target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

    response = client.get(f"/scans/{target.scan_id}")
    body = response.json()

    assert response.status_code == 200
    assert body["scan_id"] == target.scan_id
    assert body["student_nisn"] == student.nisn


def test_get_scan_by_id_returns_bare_object_not_list(client, db_session):
    """Single-item lookup should return a JSON object, not a one-item list."""
    student = make_student(db_session)
    target = make_scan(db_session, student, datetime.now(LOCAL_TZ))

    response = client.get(f"/scans/{target.scan_id}")
    body = response.json()

    assert isinstance(body, dict), "Single scan lookup should return a bare object"


def test_get_scan_by_id_missing_returns_404(client, db_session):
    """A scan_id that doesn't exist should 404, same convention as POST /scans
    for a missing student."""
    # make sure the table isn't empty, so a passing test isn't just an
    # accidental "nothing exists yet" false positive
    student = make_student(db_session)
    make_scan(db_session, student, datetime.now(LOCAL_TZ))

    response = client.get("/scans/999999")

    assert response.status_code == 404


def test_get_scan_by_id_non_integer_is_422(client):
    """FastAPI path param typed as int should reject non-numeric ids at the
    validation layer, before your route logic even runs."""
    response = client.get("/scans/not-an-id")

    assert response.status_code == 422


def test_get_scan_combines_nisn_and_date_range(client, db_session):
    student_a = make_student(db_session, nisn="1111111111", name="Student A")
    student_b = make_student(db_session, nisn="2222222222", name="Student B")

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
