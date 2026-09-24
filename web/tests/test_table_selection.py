"""Dashboard selection confirmation and atomic bulk actions."""

import pytest
from app.core.admin_auth import ADMIN_SESSION_COOKIE
from app.models.admin import Admin
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
from app.services.admin_auth_service import create_admin_session, hash_password
from app.services.class_service import get_class_directory


@pytest.fixture
def admin_client(client, db_session):
    admin = Admin(
        username="selection-admin", password_hash=hash_password("test-password")
    )
    db_session.add(admin)
    db_session.commit()
    client.cookies.set(
        ADMIN_SESSION_COOKIE, create_admin_session(db_session, admin, 1), path="/"
    )
    return client


def submit(client, kind, ids, action="delete", step="apply", **kwargs):
    return client.post(
        f"/admin/{kind}/selection/{step}",
        data={"ids": [str(i) for i in ids], "action": action},
        follow_redirects=False,
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["students", "classes"])
@pytest.mark.parametrize("step", ["confirm", "apply"])
def test_requires_admin(client, kind, step):
    response = submit(client, kind, [1], step=step)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_student_confirmation_and_subset_delete(
    admin_client, db_session, student_factory
):
    first = student_factory()
    second = student_factory(nisn="1000000002")
    ids = [first.id, second.id]
    preview = submit(
        admin_client,
        "students",
        [first.id],
        step="confirm",
        headers={"HX-Request": "true"},
    )
    assert preview.status_code == 200
    assert "Hapus 1 siswa?" in preview.text and first.nisn in preview.text
    assert 'name="ids"' in preview.text
    assert db_session.get(Student, ids[0]) is not None
    response = submit(
        admin_client, "students", [first.id], headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#student-results"
    assert db_session.get(Student, ids[0]) is None
    assert db_session.get(Student, ids[1]) is not None


def test_deactivate_keeps_student_data(admin_client, db_session, student_factory):
    first = student_factory()
    second = student_factory(nisn="1000000002")
    response = submit(
        admin_client, "students", [first.id, first.id], action="deactivate"
    )
    assert response.status_code == 303
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.current is False and second.current is True
    assert first.name == "Shaun" and first.nisn == "1000000001"


def test_bulk_student_delete_keeps_attendance_history(
    admin_client, db_session, student_factory, scan_log_factory
):
    student = student_factory()
    log = scan_log_factory(student)
    student_id, scan_id = student.id, log.scan_id

    assert submit(admin_client, "students", [student_id]).status_code == 303
    db_session.expire_all()
    assert db_session.get(Student, student_id) is None
    assert db_session.get(ScanLog, scan_id).student_id is None


def test_class_delete_unassigns_students(
    admin_client, db_session, class_factory, student_factory
):
    first = class_factory()
    second = class_factory(class_name="Other")
    student = student_factory(class_id=first.class_id)
    first_id = first.class_id
    preview = submit(admin_client, "classes", [first_id], step="confirm")
    assert preview.status_code == 200
    assert "Data siswa tetap tersimpan" in preview.text
    response = submit(admin_client, "classes", [first_id])
    assert response.status_code == 303
    db_session.expire_all()
    assert db_session.get(Class, first_id) is None
    assert db_session.get(Class, second.class_id) is not None
    assert student.class_id is None


@pytest.mark.parametrize("ids", [[], ["abc"], [-1], [999999]])
def test_invalid_selection(admin_client, ids):
    response = submit(admin_client, "students", ids)
    assert response.status_code in {409, 422}


def test_missing_record_prevents_partial_change(
    admin_client, db_session, student_factory
):
    student = student_factory()
    response = submit(
        admin_client, "students", [student.id, 999999], action="deactivate"
    )
    assert response.status_code == 409
    db_session.refresh(student)
    assert student.current


def test_invalid_action_and_csrf(admin_client, class_factory):
    cls = class_factory()
    assert (
        submit(admin_client, "classes", [cls.class_id], action="deactivate").status_code
        == 422
    )
    assert (
        submit(
            admin_client,
            "classes",
            [cls.class_id],
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )


def test_class_directory_sorted_by_id(db_session, class_factory):
    first = class_factory(class_name="Z", grade=12)
    second = class_factory(class_name="A", grade=1)
    assert [row.class_id for row in get_class_directory(db_session, None, None)] == [
        first.class_id,
        second.class_id,
    ]
