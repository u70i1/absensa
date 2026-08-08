"""Tests for GET /students."""

import pytest
from app.models.class_ import Class
from app.models.student import Student

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

SEED_STUDENTS = [
    {"name": "Shaun", "class_index": 0, "nisn": "1000000001"},
    {"name": "Ed", "class_index": 0, "nisn": "1000000002"},
    {"name": "Liz", "class_index": 0, "nisn": "1000000003"},
    {"name": "David", "class_index": 0, "nisn": "1000000004"},
    {"name": "Dianne", "class_index": 0, "nisn": "1000000005"},
    {"name": "Barbara", "class_index": 0, "nisn": "1000000006"},
    {"name": "Philip", "class_index": 0, "nisn": "1000000007"},
    {"name": "Pete", "class_index": 0, "nisn": "1000000008"},
    {"name": "Yvonne", "class_index": 1, "nisn": "1000000009"},
    {"name": "Tom", "class_index": 1, "nisn": "1000000010"},
    {"name": "Declan", "class_index": 2, "nisn": "1000000011"},
    {"name": "Alan", "class_index": 3, "nisn": "1000000100"},
]

SEED_CLASSES = ["10A", "10B", "10C", "10D"]


@pytest.fixture
def seeded_students_and_classes(db_session):
    """Insert SEED_STUDENTS and SEED_CLASSES and return them."""
    classes = [Class(class_name=class_) for class_ in SEED_CLASSES]
    db_session.add_all(classes)
    db_session.flush()
    students = [
        Student(
            name=data["name"],
            nisn=data["nisn"],
            class_id=classes[data["class_index"]].class_id,
        )
        for data in SEED_STUDENTS
    ]
    db_session.add_all(students)
    db_session.commit()
    return 0


# @pytest.fixture
# def seeded_students(db_session):
#     """Insert SEED_STUDENTS and return them."""
#     students = [Student(current=True, **data) for data in SEED_STUDENTS]
#     db_session.add_all(students)
#     db_session.commit()
#     return students

# @pytest.fixture
# def seeded_classes(db_session):
#     """Insert SEED_CLASSES and return them."""
#     classes = [Class(**data) for data in SEED_CLASSES]
#     db_session.add_all(classes)
#     db_session.commit()
#     return classes


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_default_page_size_is_10(client, seeded_students_and_classes):
    response = client.get("/students")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 10


def test_page_2_returns_remaining_students(client, seeded_students_and_classes):
    """11 seeded students, limit=10 -> page 2 should hold the last 2."""
    response = client.get("/students?page=2&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2


def test_custom_limit_per_page(client, seeded_students_and_classes):
    response = client.get("/students?limit=5")

    assert response.status_code == 200
    assert len(response.json()) == 5


def test_page_and_limit_do_not_repeat_rows(client, seeded_students_and_classes):
    """Page 1 and page 2 (limit=5) should never share a student."""
    page1 = client.get("/students?page=1&limit=5").json()
    page2 = client.get("/students?page=2&limit=5").json()

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


def test_filter_by_class(client, seeded_students_and_classes):
    response = client.get("/students?class=10B&limit=100")

    assert response.status_code == 200
    body = response.json()
    names = {s["name"] for s in body}
    assert names == {"Yvonne", "Tom"}


def test_filter_by_class_no_match(client, seeded_students_and_classes):
    response = client.get("/students?class=99Z")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# name filter (substring, case-insensitive)
# ---------------------------------------------------------------------------


def test_filter_by_name_substring(client, seeded_students_and_classes):
    """'lan' should match both Declan and Alan."""
    response = client.get("/students?name=lan")

    assert response.status_code == 200
    names = {s["name"] for s in response.json()}
    assert names == {"Declan", "Alan"}


def test_filter_by_name_is_case_insensitive(client, seeded_students_and_classes):
    response = client.get("/students?name=SHAUN")

    assert response.status_code == 200
    names = {s["name"] for s in response.json()}
    assert names == {"Shaun"}


def test_filter_by_name_no_match(client, seeded_students_and_classes):
    response = client.get("/students?name=zzz")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# nisn filter (exact match)
# ---------------------------------------------------------------------------


def test_filter_by_nisn_exact_match(client, seeded_students_and_classes):
    response = client.get("/students?nisn=1000000003")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Liz"


def test_filter_by_nisn_no_match(client, seeded_students_and_classes):
    response = client.get("/students?nisn=0000000000")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# combined filters
# ---------------------------------------------------------------------------


def test_combined_class_and_name_filters(client, seeded_students_and_classes):
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
