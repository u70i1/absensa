"""Automatic workbook detection and transactional archive/photo imports."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from struct import pack
import tarfile
from zipfile import ZIP_DEFLATED, ZipFile
from zlib import crc32

import libarchive
from PIL import Image
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.class_ import Class
from app.models.import_batch import ImportBatch, ImportPhoto
from app.models.student import Student
from app.services import import_archive_service, import_service, student_photo_service, student_service
from app.services.exceptions import AppException
from tests.test_import import batch_for, importer, workbook_bytes  # noqa: F401


@pytest.fixture(autouse=True)
def photo_directory(tmp_path, monkeypatch):
    path = tmp_path / "photos"
    monkeypatch.setattr(settings, "photos_dir", str(path))
    return path


def photo_bytes():
    stream = BytesIO()
    Image.new("RGB", (24, 24), "red").save(stream, "PNG")
    return stream.getvalue()


def student_row(nisn="0012345678", student_id=None):
    return [student_id, "Imported student", None, nisn, "Aktif", None]


def zip_bytes(files):
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()


def stored_rar(files):
    """Generate a small RAR4 fixture using the uncompressed storage method."""
    def header(body):
        return pack("<H", crc32(body) & 0xffff) + body

    result = b"Rar!\x1a\x07\x00" + header(pack("<BHHHI", 0x73, 0, 13, 0, 0))
    for name, content in files.items():
        name = name.encode()
        result += header(pack(
            "<BHHIIBIIBBHI", 0x74, 0x8000, 32 + len(name), len(content),
            len(content), 3, crc32(content), 0, 20, 0x30, len(name), 0o100644,
        ) + name) + content
    return result + header(pack("<BHH", 0x7b, 0, 7))


def upload(client, content, name="data.zip"):
    return client.post("/admin/import/preview", files={"file": (name, content)}, follow_redirects=False)


def confirm(client, batch, rows=None):
    keys = [row["key"] for row in batch.payload["rows"]] if rows is None else rows
    return client.post(f"/admin/import/{batch.token}/confirm", data={"selected": keys}, follow_redirects=False)


@pytest.mark.parametrize("kind,rows", [("students", [student_row()]), ("classes", [[None, 10, "10A"]])])
def test_xlsx_detected_without_kind_or_filename_hint(client, importer, db_session, kind, rows):
    batch, _ = batch_for(upload(client, workbook_bytes(kind, rows), "anything.xlsx"), client, db_session)
    assert batch.kind == kind
    assert not batch.payload["errors"]
    assert confirm(client, batch).status_code == 303


@pytest.mark.parametrize("suffix,format_,filter_", [
    ("zip", "zip", None), ("rar", None, None), ("7z", "7zip", None),
    ("tar", "ustar", None), ("tar.gz", "ustar", "gzip"),
    ("tar.bz2", "ustar", "bzip2"), ("tar.xz", "ustar", "xz"),
])
def test_archive_formats_end_to_end(client, importer, db_session, tmp_path, suffix, format_, filter_):
    files = {"data.xlsx": workbook_bytes("students", [student_row()]), "photos/0012345678.png": photo_bytes()}
    if suffix == "rar":
        content = stored_rar(files)
    else:
        path = tmp_path / f"test.{suffix}"
        with libarchive.file_writer(str(path), format_, filter_) as archive:
            for name, data in files.items():
                archive.add_file_from_memory(name, len(data), data)
        content = path.read_bytes()
    batch, page = batch_for(upload(client, content, f"file.{suffix}"), client, db_session)
    assert "Foto baru" in page.text
    assert batch.payload["photo_count"] == 1
    assert confirm(client, batch).status_code == 303
    student = db_session.scalar(select(Student))
    assert student.nisn == "0012345678"
    assert student_photo_service.photo_file(student.photo_path).is_file()
    assert db_session.scalar(select(func.count()).select_from(ImportPhoto)) == 0


def test_mixed_workbooks_unique_row_keys_and_optional_photos(client, importer, db_session, photo_directory):
    files = {
        "kelas.xlsx": workbook_bytes("classes", [[None, 10, "10A"]]),
        "siswa-a.xlsx": workbook_bytes("students", [student_row()]),
        "siswa-b.xlsx": workbook_bytes("students", [student_row("0012345679")]),
        "photos/0012345678.png": photo_bytes(),
    }
    batch, page = batch_for(upload(client, zip_bytes(files)), client, db_session)
    assert batch.kind == "mixed"
    assert not batch.payload["errors"]  # A missing photo is expected and not an error.
    assert len({row["key"] for row in batch.payload["rows"]}) == 3
    assert "siswa-a.xlsx" in page.text and "siswa-b.xlsx" in page.text
    assert db_session.scalar(select(func.count()).select_from(Student)) == 0
    assert not photo_directory.exists()
    photo = client.get(f"/admin/import/{batch.token}/photos/0012345678")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    assert confirm(client, batch).status_code == 303
    assert db_session.scalar(select(func.count()).select_from(Student)) == 2
    assert db_session.scalar(select(func.count()).select_from(Class)) == 1
    missing_photo_student = db_session.scalar(select(Student).where(Student.nisn == "0012345679"))
    assert missing_photo_student.photo_path is None


def test_wrapper_folder_and_os_metadata(client, importer, db_session):
    batch, _ = batch_for(upload(client, zip_bytes({
        "School/data.xlsx": workbook_bytes("classes", [[None, 10, "10A"]]),
        "School/photos/": b"", "School/.DS_Store": b"ignored", "__MACOSX/._data.xlsx": b"ignored",
    })), client, db_session)
    assert not batch.payload["errors"]
    assert confirm(client, batch).status_code == 303


@pytest.mark.parametrize("bad_path", ["../outside.xlsx", "/absolute.xlsx", "C:/file.xlsx", "nested/deeper/data.xlsx", "photos/not-a-nisn.png", "photos/123.png", "photos/0012345678.svg"])
def test_invalid_structure_and_photo_credentials(client, importer, bad_path):
    response = upload(client, zip_bytes({"data.xlsx": workbook_bytes("students", [student_row()]), bad_path: b"invalid"}))
    assert response.status_code == 422
    assert "File tidak dapat diproses" in response.text


def test_present_invalid_and_unmatched_photos_are_reported(client, importer, db_session):
    batch, page = batch_for(upload(client, zip_bytes({
        "data.xlsx": workbook_bytes("students", [student_row()]),
        "photos/0012345678.png": b"not an image",
        "photos/9999999999.png": photo_bytes(),
    })), client, db_session)
    assert len(batch.payload["rows"]) == 1
    assert len(batch.payload["errors"]) == 2
    assert "photos/0012345678.png" in page.text and "photos/9999999999.png" in page.text
    assert batch.payload["photo_count"] == 0


def test_duplicates_across_workbooks_and_duplicate_photos(client, importer, db_session):
    content = workbook_bytes("students", [student_row()])
    batch, _ = batch_for(upload(client, zip_bytes({"one.xlsx": content, "two.xlsx": content})), client, db_session)
    assert not batch.payload["rows"]
    assert {e["file"] for e in batch.payload["errors"]} == {"one.xlsx", "two.xlsx"}
    response = upload(client, zip_bytes({"data.xlsx": content, "photos/0012345678.png": photo_bytes(), "photos/0012345678.jpg": photo_bytes()}))
    assert response.status_code == 422


def test_exclusion_and_cancel_never_write_photos(client, importer, db_session, photo_directory):
    content = zip_bytes({"data.xlsx": workbook_bytes("students", [student_row(), student_row("0012345679")]), "photos/0012345678.png": photo_bytes()})
    batch, _ = batch_for(upload(client, content), client, db_session)
    selected = [r["key"] for r in batch.payload["rows"] if r["values"]["nisn"] == "0012345679"]
    assert confirm(client, batch, selected).status_code == 303
    assert not photo_directory.exists()
    assert db_session.scalar(select(func.count()).select_from(ImportPhoto)) == 0
    batch, _ = batch_for(upload(client, zip_bytes({"data.xlsx": workbook_bytes("students", [student_row()]), "photos/0012345678.png": photo_bytes()})), client, db_session)
    assert client.post(f"/admin/import/{batch.token}/cancel").status_code == 200
    assert db_session.scalar(select(func.count()).select_from(ImportPhoto)) == 0
    assert not photo_directory.exists()


def test_existing_photo_preserved_without_replacement(client, importer, db_session, existing_student):
    existing_student.photo_path = "existing.jpg"
    db_session.commit()
    batch, _ = batch_for(upload(client, zip_bytes({"data.xlsx": workbook_bytes("students", [student_row(existing_student.nisn, existing_student.id)])})), client, db_session)
    assert not batch.payload["errors"]
    assert confirm(client, batch).status_code == 303
    db_session.refresh(existing_student)
    assert existing_student.photo_path == "existing.jpg"


def test_replacement_cleanup_and_stale_photo_protection(client, importer, db_session, existing_student):
    original = student_photo_service.update_student_photo(db_session, existing_student.id, BytesIO(photo_bytes()))
    content = zip_bytes({"data.xlsx": workbook_bytes("students", [student_row(existing_student.nisn, existing_student.id)]), f"photos/{existing_student.nisn}.png": photo_bytes()})
    batch, _ = batch_for(upload(client, content), client, db_session)
    assert student_photo_service.photo_file(original).exists()
    assert confirm(client, batch).status_code == 303
    db_session.refresh(existing_student)
    assert existing_student.photo_path != original
    assert not student_photo_service.photo_file(original).exists()
    batch, _ = batch_for(upload(client, content), client, db_session)
    latest = student_photo_service.update_student_photo(db_session, existing_student.id, BytesIO(photo_bytes()))
    assert confirm(client, batch).status_code == 409
    assert student_photo_service.photo_file(latest).exists()


def test_photo_rollback_if_later_data_write_fails(client, importer, db_session, photo_directory, monkeypatch):
    batch, _ = batch_for(upload(client, zip_bytes({
        "data.xlsx": workbook_bytes("students", [student_row(), student_row("0012345679")]),
        "photos/0012345678.png": photo_bytes(),
    })), client, db_session)
    original = student_service.post_student

    def fail_second(*args, **kwargs):
        if kwargs["nisn"] == "0012345679":
            raise AppException("simulated failure", 409)
        return original(*args, **kwargs)

    monkeypatch.setattr(student_service, "post_student", fail_second)
    assert confirm(client, batch).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Student)) == 0
    assert not list(photo_directory.glob("*.jpg"))
    assert db_session.scalar(select(func.count()).select_from(ImportPhoto)) == 1


def test_preview_photo_authorization_expiry_and_cleanup(client, importer, db_session):
    content = zip_bytes({"data.xlsx": workbook_bytes("students", [student_row()]), "photos/0012345678.png": photo_bytes()})
    batch, _ = batch_for(upload(client, content), client, db_session)
    with pytest.raises(AppException):
        import_service.get_preview_photo(db_session, importer.id + 1, batch.token, "0012345678")
    token = batch.token
    batch.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(f"/admin/import/{token}/photos/0012345678").status_code == 404
    assert upload(client, content).status_code == 303
    db_session.expire_all()
    assert db_session.get(ImportPhoto, (token, "0012345678")) is None


def test_symlinks_and_archive_limits(client, importer, monkeypatch):
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        link = tarfile.TarInfo("data.xlsx")
        link.type = tarfile.SYMTYPE
        link.linkname = "/tmp/outside"
        archive.addfile(link)
    assert upload(client, stream.getvalue(), "bad.tar").status_code == 422
    monkeypatch.setattr(import_archive_service, "MAX_EXPANDED_BYTES", 10)
    assert upload(client, zip_bytes({"data.xlsx": b"x" * 20})).status_code == 413


def test_global_row_limit_and_bad_workbook_reporting(client, importer, db_session, monkeypatch):
    content = workbook_bytes("classes", [[None, 10, "10A"]])
    batch, page = batch_for(upload(client, zip_bytes({"good.xlsx": content, "broken.xlsx": b"bad"})), client, db_session)
    assert len(batch.payload["rows"]) == 1
    assert "broken.xlsx" in page.text
    monkeypatch.setattr(import_service, "MAX_ROWS", 1)
    assert upload(client, zip_bytes({"one.xlsx": content, "two.xlsx": content})).status_code == 413
