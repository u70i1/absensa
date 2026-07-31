"""Tests for GET /students."""

import pytest
from app.models.student import Student

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

SEED_STUDENTS = [
    {"name": "Shaun", "class_": "10A", "nisn": "1000000001"},
    {"name": "Ed", "class_": "10A", "nisn": "1000000002"},
    {"name": "Liz", "class_": "10A", "nisn": "1000000003"},
    {"name": "David", "class_": "10A", "nisn": "1000000004"},
    {"name": "Dianne", "class_": "10A", "nisn": "1000000005"},
    {"name": "Barbara", "class_": "10A", "nisn": "1000000006"},
    {"name": "Philip", "class_": "10A", "nisn": "1000000007"},
    {"name": "Pete", "class_": "10A", "nisn": "1000000008"},
    {"name": "Yvonne", "class_": "10B", "nisn": "1000000009"},
    {"name": "Tom", "class_": "10B", "nisn": "1000000010"},
    {"name": "Declan", "class_": "10C", "nisn": "1000000011"},
    {"name": "Alan", "class_": "10D", "nisn": "1000000100"},
]


@pytest.fixture
def seeded_students(db_session):
    """Insert SEED_STUDENTS and return them."""
    students = [Student(current=True, **data) for data in SEED_STUDENTS]
    db_session.add_all(students)
    db_session.commit()
    return students


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_default_page_size_is_10(client, seeded_students):
    response = client.get("/students")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 10


def test_page_2_returns_remaining_students(client, seeded_students):
    """11 seeded students, amount=10 -> page 2 should hold the last 1."""
    response = client.get("/students?page=2&amount=10")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1


def test_custom_amount_per_page(client, seeded_students):
    response = client.get("/students?amount=5")

    assert response.status_code == 200
    assert len(response.json()) == 5


def test_page_and_amount_do_not_repeat_rows(client, seeded_students):
    """Page 1 and page 2 (amount=5) should never share a student."""
    page1 = client.get("/students?page=1&amount=5").json()
    page2 = client.get("/students?page=2&amount=5").json()

    ids_page1 = {s["id"] for s in page1}
    ids_page2 = {s["id"] for s in page2}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.mark.parametrize("bad_page", [0, -1])
def test_invalid_page_is_rejected(client, bad_page):
    response = client.get(f"/students?page={bad_page}")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# class filter
# ---------------------------------------------------------------------------


def test_filter_by_class(client, seeded_students):
    response = client.get("/students?class=10B&amount=100")

    assert response.status_code == 200
    body = response.json()
    names = {s["name"] for s in body}
    assert names == {"Tom", "Declan"}


def test_filter_by_class_no_match(client, seeded_students):
    response = client.get("/students?class=99Z")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# name filter (substring, case-insensitive)
# ---------------------------------------------------------------------------


def test_filter_by_name_substring(client, seeded_students):
    """'lan' should match both Declan and Alan."""
    response = client.get("/students?name=lan")

    assert response.status_code == 200
    names = {s["name"] for s in response.json()}
    assert names == {"Declan", "Alan"}


def test_filter_by_name_is_case_insensitive(client, seeded_students):
    response = client.get("/students?name=SHAUN")

    assert response.status_code == 200
    names = {s["name"] for s in response.json()}
    assert names == {"Shaun"}


def test_filter_by_name_no_match(client, seeded_students):
    response = client.get("/students?name=zzz")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# nisn filter (exact match)
# ---------------------------------------------------------------------------


def test_filter_by_nisn_exact_match(client, seeded_students):
    response = client.get("/students?nisn=1000000003")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Liz"


def test_filter_by_nisn_no_match(client, seeded_students):
    response = client.get("/students?nisn=0000000000")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# combined filters
# ---------------------------------------------------------------------------


def test_combined_class_and_name_filters(client, seeded_students):
    """class=10B narrows to Yvonne+Tom, then name=yvon narrows further to Yvonne."""
    response = client.get("/students?class=10B&name=yvon")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Yvonne"


# ---------------------------------------------------------------------------
# empty database
# ---------------------------------------------------------------------------


def test_no_students_returns_empty_list(client):
    response = client.get("/students")

    assert response.status_code == 200
    assert response.json() == []
