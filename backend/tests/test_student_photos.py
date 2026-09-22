"""Photo upload authorization, validation, persistence, and failure recovery."""

from io import BytesIO

from app.core.admin_auth import ADMIN_SESSION_COOKIE
from app.core.config import settings
from app.models.admin import Admin
from app.services.admin_auth_service import create_admin_session
from app.services import student_photo_service
from PIL import Image
import pytest


def image_bytes(format="PNG", size=(40, 30)):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, format=format)
    return output.getvalue()


@pytest.fixture
def photos_dir(tmp_path, monkeypatch):
    directory = tmp_path / "photos"
    monkeypatch.setattr(settings, "photos_dir", str(directory))
    return directory


@pytest.fixture
def photo_admin(client, db_session, photos_dir):
    admin = Admin(username="photo-admin", password_hash="unused")
    db_session.add(admin)
    db_session.commit()
    token = create_admin_session(db_session, admin, 1)
    client.cookies.set(ADMIN_SESSION_COOKIE, token, path="/admin")
    return client


def upload(client, student_id, content=None, filename="portrait.png"):
    return client.post(
        f"/admin/students/{student_id}/photo",
        files={"photo": (filename, image_bytes() if content is None else content, "image/png")},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )


def test_photo_requires_admin_for_upload_and_view(client, existing_student, photos_dir):
    assert upload(client, existing_student.id).status_code == 401
    assert client.get(
        f"/admin/students/{existing_student.id}/photo", follow_redirects=False
    ).status_code == 303
    assert existing_student.photo_path is None
    assert not photos_dir.exists()


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_photo_round_trip_and_dashboard(photo_admin, existing_student, photos_dir, format):
    response = upload(photo_admin, existing_student.id, image_bytes(format), "../../outside.png")
    assert response.status_code == 200
    result = response.json()
    assert existing_student.photo_path == result["photo_path"]
    stored = photos_dir / result["photo_path"]
    assert stored.is_file()
    assert stored.parent == photos_dir
    photo = photo_admin.get(result["photo_url"])
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/jpeg"
    assert photo.headers["cache-control"] == "private, no-store"
    with Image.open(BytesIO(photo.content)) as image:
        assert image.format == "JPEG"
        assert image.size == (40, 30)
    assert result["photo_path"] in photo_admin.get("/students").text
    assert result["photo_path"] in photo_admin.get("/admin/students").text
    assert result["photo_path"] in photo_admin.get(
        f"/admin/students/{existing_student.id}/edit"
    ).text


def test_replacing_photo_removes_old_file(photo_admin, existing_student, photos_dir):
    first = upload(photo_admin, existing_student.id).json()["photo_path"]
    second = upload(photo_admin, existing_student.id).json()["photo_path"]
    assert first != second
    assert not (photos_dir / first).exists()
    assert (photos_dir / second).exists()
    assert existing_student.photo_path == second


def test_editing_student_preserves_and_returns_photo(photo_admin, existing_student):
    filename = upload(photo_admin, existing_student.id).json()["photo_path"]
    payload = {
        "id": existing_student.id, "nisn": existing_student.nisn,
        "name": "Updated name", "current": True, "class_id": existing_student.class_id,
    }
    response = photo_admin.put("/students/bulk", json=[payload])
    assert response.status_code == 200
    assert response.json()["succeeded"][0]["item"]["photo_path"] == filename
    response = photo_admin.put(f"/students/{existing_student.id}", json=payload)
    assert response.status_code == 200
    assert response.json()["photo_path"] == filename
    students = photo_admin.get(f"/classes/{existing_student.class_id}/students").json()
    assert students[0]["photo_path"] == filename


@pytest.mark.parametrize("content,status", [
    (b"", 415),
    (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", 415),
    (b"not really a PNG", 415),
    (image_bytes("GIF"), 415),
    (image_bytes()[:40], 415),
    (b"x" * (student_photo_service.MAX_PHOTO_BYTES + 1), 413),
])
def test_invalid_upload_preserves_previous_photo(
    photo_admin, existing_student, photos_dir, content, status
):
    first = upload(photo_admin, existing_student.id).json()["photo_path"]
    response = upload(photo_admin, existing_student.id, content)
    assert response.status_code == status
    assert existing_student.photo_path == first
    assert [file.name for file in photos_dir.iterdir()] == [first]


def test_pixel_limit(photo_admin, existing_student, photos_dir, monkeypatch):
    monkeypatch.setattr(student_photo_service, "MAX_PHOTO_PIXELS", 100)
    assert upload(photo_admin, existing_student.id).status_code == 413
    assert not photos_dir.exists()


def test_missing_student_and_photo(photo_admin, existing_student, photos_dir):
    assert upload(photo_admin, 2147483647).status_code == 404
    assert photo_admin.get(f"/admin/students/{existing_student.id}/photo").status_code == 404
    assert not photos_dir.exists()


def test_commit_failure_preserves_previous_photo(
    photo_admin, existing_student, photos_dir, db_session, monkeypatch
):
    first = upload(photo_admin, existing_student.id).json()["photo_path"]

    def fail_commit():
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated database failure"):
        student_photo_service.update_student_photo(db_session, existing_student.id, BytesIO(image_bytes()))
    assert existing_student.photo_path == first
    assert [file.name for file in photos_dir.iterdir()] == [first]


def test_stored_path_cannot_escape_photo_directory(
    photo_admin, existing_student, photos_dir, db_session
):
    existing_student.photo_path = "../outside.jpg"
    db_session.commit()
    assert photo_admin.get(f"/admin/students/{existing_student.id}/photo").status_code == 404
