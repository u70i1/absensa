"""Production transaction boundaries and pre-launch data-integrity regressions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from time import sleep
from uuid import uuid4

import pytest
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
from app.schemas.class_ import ClassBulkDeleteRequest, ClassBulkUpdateRequest
from app.schemas.scan import ScanBulkDeleteRequest, ScanListQuery
from app.schemas.student import StudentBulkDeleteRequest, StudentBulkUpdateRequest
from app.services import (
    class_bulk_service,
    class_service,
    scan_bulk_service,
    scan_service,
    student_bulk_service,
    student_service,
)
from app.services.exceptions import AppException
from sqlalchemy import create_engine, delete, event, func, select, text
from sqlalchemy.orm import Session


@pytest.mark.parametrize("kind", ["students", "classes", "scans"])
def test_bulk_delete_survives_session_close(engine, kind):
    """The request's session closing must not undo a successful delete."""
    with Session(engine) as db:
        item = Class(grade=10, class_name=uuid4().hex[:20])
        db.add(item)
        db.flush()
        class_id = item.class_id
        student = Student(name="Audit", nisn="9900000001", class_id=class_id)
        db.add(student)
        db.flush()
        student_id = student.id
        scan = ScanLog(student_id=student.id, name=student.name)
        db.add(scan)
        db.commit()
        scan_id = scan.scan_id
    operations = {
        "students": (
            student_bulk_service.delete_students_bulk,
            StudentBulkDeleteRequest,
            Student,
            student_id,
        ),
        "classes": (
            class_bulk_service.delete_classes_bulk,
            ClassBulkDeleteRequest,
            Class,
            class_id,
        ),
        "scans": (
            scan_bulk_service.delete_scans_bulk,
            ScanBulkDeleteRequest,
            ScanLog,
            scan_id,
        ),
    }
    operation, schema, model, identity = operations[kind]
    try:
        with Session(engine) as db:
            assert operation(db, schema(ids=[identity]), False) is None
        with Session(engine) as db:
            assert db.get(model, identity) is None
    finally:
        with Session(engine) as db:
            db.execute(delete(ScanLog).where(ScanLog.scan_id == scan_id))
            db.execute(delete(Student).where(Student.id == student_id))
            db.execute(delete(Class).where(Class.class_id == class_id))
            db.commit()


def test_concurrent_scans_record_one_attendance(engine):
    with Session(engine) as db:
        student = Student(name="Concurrent scan", nisn="9900000002", current=True)
        db.add(student)
        db.commit()
        student_id, nisn = student.id, student.nisn
    barrier = Barrier(2)

    def delay_insert(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO scan_logs"):
            # Give the competing request time to reach the duplicate check.
            sleep(0.2)

    def scan(_):
        barrier.wait(timeout=10)
        with Session(engine) as db:
            try:
                scan_service.post_scan(db, nisn)
                return 200
            except AppException as exc:
                return exc.status_code

    event.listen(engine, "before_cursor_execute", delay_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(scan, range(2))) == [200, 409]
        with Session(engine) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(ScanLog)
                    .where(ScanLog.student_id == student_id)
                )
                == 1
            )
    finally:
        event.remove(engine, "before_cursor_execute", delay_insert)
        with Session(engine) as db:
            db.execute(delete(ScanLog).where(ScanLog.student_id == student_id))
            db.execute(delete(Student).where(Student.id == student_id))
            db.commit()


def test_scan_accepts_twenty_character_class_and_returns_nisn(
    client, authenticated_data_api, existing_student, db_session
):
    existing_student.class_.class_name = "A" * 20
    db_session.commit()
    response = client.post("/scans", json={"nisn": existing_student.nisn})
    assert response.status_code == 200
    assert response.json()["class_name"] == "A" * 20
    assert response.json()["nisn"] == existing_student.nisn


@pytest.mark.parametrize("bulk", [False, True])
def test_omitted_guardian_contact_is_preserved(
    client, authenticated_data_api, existing_student, db_session, bulk
):
    existing_student.guardian_phone = "081234567890"
    db_session.commit()
    payload = {
        "name": "Edited",
        "nisn": existing_student.nisn,
        "class_id": existing_student.class_id,
        "current": True,
    }
    if bulk:
        response = client.put(
            "/students/bulk", json=[{"id": existing_student.id, **payload}]
        )
    else:
        response = client.put(f"/students/{existing_student.id}", json=payload)
    assert response.status_code == 200
    db_session.refresh(existing_student)
    assert existing_student.guardian_phone == "081234567890"
    payload["guardian_phone"] = None
    if bulk:
        response = client.put(
            "/students/bulk", json=[{"id": existing_student.id, **payload}]
        )
    else:
        response = client.put(f"/students/{existing_student.id}", json=payload)
    assert response.status_code == 200
    db_session.refresh(existing_student)
    assert existing_student.guardian_phone is None


@pytest.mark.parametrize("dry_run", [False, True])
def test_rejected_student_cannot_free_nisn_for_swap(
    db_session, student_factory, dry_run
):
    first = student_factory(nisn="9900000011")
    second = student_factory(nisn="9900000012")
    third = student_factory(nisn="9900000013")
    requests = [
        StudentBulkUpdateRequest(
            id=first.id, name="First", nisn=second.nisn, current=True
        ),
        StudentBulkUpdateRequest(
            id=second.id,
            name="Second",
            nisn="9900000014",
            class_id=2147483647,
            current=True,
        ),
        StudentBulkUpdateRequest(
            id=third.id, name="Third", nisn="9900000015", current=True
        ),
    ]
    result = student_bulk_service.update_students_bulk(db_session, requests, dry_run)
    assert [entry["index"] for entry in result["succeeded"]] == [2]
    assert {entry["index"] for entry in result["failed"]} == {0, 1}


@pytest.mark.parametrize("dry_run", [False, True])
def test_rejected_class_cannot_free_name_for_swap(db_session, class_factory, dry_run):
    first = class_factory(class_name="First")
    second = class_factory(class_name="Second")
    third = class_factory(class_name="Third")
    requests = [
        ClassBulkUpdateRequest(class_id=first.class_id, class_name="Second", grade=10),
        ClassBulkUpdateRequest(class_id=second.class_id, class_name="X" * 21, grade=10),
        ClassBulkUpdateRequest(class_id=third.class_id, class_name="Changed", grade=10),
    ]
    result = class_bulk_service.update_classes_bulk(db_session, requests, dry_run)
    assert [entry["index"] for entry in result["succeeded"]] == [2]
    assert {entry["index"] for entry in result["failed"]} == {0, 1}


def test_naive_scan_dates_use_school_timezone(
    db_session, existing_student, scan_log_factory
):
    midnight = datetime(2026, 9, 24, tzinfo=scan_service.tz_info)
    scan = scan_log_factory(existing_student, midnight + timedelta(minutes=1))
    query = ScanListQuery(date_from="2026-09-24", date_to="2026-09-24")
    assert [
        row.scan_id for row in scan_service.get_scan(db_session, **query.model_dump())
    ] == [scan.scan_id]


def test_scan_query_handles_mixed_timezone_bounds():
    query = ScanListQuery(date_from="2026-09-24", date_to="2026-09-24T23:00:00+07:00")
    assert query.date_from is not None


@pytest.mark.parametrize(
    "changes",
    [
        {"nisn": "abcdefghij"},
        {"nisn": "１２３４５６７８９０"},
        {"name": "A" * 256},
        {"class_id": 0},
    ],
)
def test_student_api_rejects_invalid_identity(client, authenticated_data_api, changes):
    response = client.post(
        "/students",
        json={
            "name": "Audit",
            "nisn": "9900000003",
            "class_id": None,
            "current": True,
            **changes,
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("kind", ["student", "class"])
def test_concurrent_creates_report_conflict_without_corrupting_session(engine, kind):
    barrier = Barrier(2)
    name = uuid4().hex[:20]
    table = "students" if kind == "student" else "classes"

    def synchronize_insert(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith(f"INSERT INTO {table}"):
            barrier.wait(timeout=10)

    def create(_):
        with Session(engine) as db:
            try:
                if kind == "student":
                    student_service.post_student(db, "9900000081", name, None, True)
                else:
                    class_service.post_class(db, name, 10)
                return 201
            except AppException as exc:
                assert db.scalar(select(func.count()).select_from(Student)) is not None
                return exc.status_code

    event.listen(engine, "before_cursor_execute", synchronize_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(create, range(2))) == [201, 409]
    finally:
        event.remove(engine, "before_cursor_execute", synchronize_insert)
        with Session(engine) as db:
            db.execute(delete(Student).where(Student.nisn == "9900000081"))
            db.execute(delete(Class).where(Class.class_name == name))
            db.commit()


def test_pool_recovers_a_dropped_database_connection(engine):
    pool = create_engine(engine.url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    try:
        with pool.connect() as connection:
            backend = connection.scalar(text("SELECT pg_backend_pid()"))
        with engine.connect() as killer:
            assert (
                killer.scalar(
                    text("SELECT pg_terminate_backend(:pid)"), {"pid": backend}
                )
                is True
            )
        with pool.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
            assert connection.scalar(text("SELECT pg_backend_pid()")) != backend
    finally:
        pool.dispose()


@pytest.mark.parametrize("kind", ["students", "classes"])
def test_repeated_bulk_update_ids_fail_each_row(
    client, authenticated_data_api, existing_student, kind
):
    if kind == "students":
        payload = [
            {
                "id": existing_student.id,
                "name": "First",
                "nisn": "9900000082",
                "current": True,
            },
            {
                "id": existing_student.id,
                "name": "Second",
                "nisn": "9900000083",
                "current": True,
            },
        ]
    else:
        payload = [
            {"class_id": existing_student.class_id, "class_name": "First", "grade": 10},
            {
                "class_id": existing_student.class_id,
                "class_name": "Second",
                "grade": 10,
            },
        ]
    response = client.put(f"/{kind}/bulk", json=payload)
    assert response.status_code == 422
    assert response.json()["succeeded"] == []
    assert len(response.json()["failed"]) == 2


@pytest.mark.parametrize("grade,name", [(0, "Valid"), (21, "Valid"), (10, "")])
def test_bulk_class_validation_matches_single_write(
    client, authenticated_data_api, grade, name
):
    response = client.post("/classes/bulk", json=[{"grade": grade, "class_name": name}])
    assert response.status_code == 422
