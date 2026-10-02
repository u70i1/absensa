"""Backup service behavior uses a disposable database and mocked external tools."""

import base64
import json
import os
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.config import settings
from app.models.backup import Backup, BackupSettings
from app.services import backup_service as backups
from app.services.backup_crypto_service import (
    EncryptedWriter,
    decrypt_archive,
    encryption_key,
    verify_archive,
)
from app.services.exceptions import AppException
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session


def make_backup(db, storage, *, when=None, status="success"):
    backup = Backup(
        id=uuid4().hex,
        created_at=when or datetime.now(UTC),
        kind="manual",
        status=status,
        phase="complete",
    )
    db.add(backup)
    db.commit()
    if status == "success":
        fake_archive(backup, storage, None)
    return backup


def fake_archive(backup, storage, bind):
    path = storage.path(backup.id)
    with path.open("wb") as output:
        writer = EncryptedWriter(output, encryption_key())
        writer.write(b"mock database/photo tar")
        writer.finish()
    return path


def test_encryption_roundtrip_and_authentication(backup_storage, tmp_path):
    source = tmp_path / "encrypted"
    plaintext = b"private data" * 200000
    with source.open("wb") as output:
        writer = EncryptedWriter(output, encryption_key())
        writer.write(plaintext[:100])
        writer.write(plaintext[100:])
        writer.finish()
    assert b"private data" not in source.read_bytes()
    decoded = tmp_path / "decoded"
    decrypt_archive(source, decoded, encryption_key())
    verify_archive(source, encryption_key())
    assert decoded.read_bytes() == plaintext
    assert decoded.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        decrypt_archive(source, decoded, encryption_key())
    damaged = bytearray(source.read_bytes())
    damaged[100] ^= 1
    source.write_bytes(damaged)
    with pytest.raises(InvalidTag):
        verify_archive(source, encryption_key())
    failed = tmp_path / "failed"
    with pytest.raises(InvalidTag):
        decrypt_archive(source, failed, encryption_key())
    assert not failed.exists()
    assert not failed.with_name("failed.partial").exists()


@pytest.mark.parametrize(
    "key", ["", "not base64!", base64.b64encode(b"short").decode()]
)
def test_missing_or_invalid_key_fails_closed(monkeypatch, key):
    monkeypatch.setattr(settings, "backup_encryption_key", SecretStr(key))
    with pytest.raises(AppException) as exc:
        encryption_key()
    assert exc.value.status_code == 503
    assert key not in str(exc.value) if key else True


@pytest.mark.parametrize(
    "times", ["25:00", "9:00", "10:00,17:00,18:00", "../secret", "10:00, 17:00"]
)
def test_invalid_schedule(times):
    with pytest.raises(AppException):
        backups.normalize_times(times)


def test_schedule_school_timezone_and_latest_catchup(backup_storage):
    config = SimpleNamespace(enabled=True, times="10:00,17:00")
    assert backups.due_slot(config, datetime(2026, 10, 2, 2, 59, tzinfo=UTC)) is None
    assert (
        backups.due_slot(config, datetime(2026, 10, 2, 3, 0, tzinfo=UTC))
        == "2026-10-02T10:00@Asia/Jakarta"
    )
    assert (
        backups.due_slot(config, datetime(2026, 10, 2, 10, 1, tzinfo=UTC))
        == "2026-10-02T17:00@Asia/Jakarta"
    )
    config.enabled = False
    assert backups.due_slot(config, datetime.now(UTC)) is None


def test_queue_is_durable_and_duplicate_jobs_reuse_active(db_session, backup_storage):
    first = backups.enqueue(db_session)
    assert first.status == "queued"
    assert backups.enqueue(db_session).id == first.id
    first.status = "failed"
    db_session.commit()
    scheduled = backups.enqueue(db_session, slot="2026-10-02T10:00@Asia/Jakarta")
    scheduled.status = "failed"
    db_session.commit()
    assert backups.enqueue(db_session, slot=scheduled.slot).id == scheduled.id


def test_job_lock_blocks_other_database_connection(db_session, engine, backup_storage):
    with engine.connect() as owner:
        assert owner.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": backups.LOCK_ID}
        )
        try:
            with pytest.raises(AppException) as exc:
                backups.enqueue(db_session)
            assert exc.value.status_code == 409
            assert backups.process_tick(engine) == "busy"
        finally:
            owner.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": backups.LOCK_ID}
            )


def test_defaults_and_validated_configuration(db_session, backup_storage, monkeypatch):
    config = backups.get_settings(db_session)
    assert (config.times, config.daily, config.weekly, config.monthly) == (
        "10:00,17:00",
        14,
        8,
        3,
    )
    config = backups.update_settings(
        db_session,
        enabled=True,
        times="17:00,10:00",
        daily=2,
        weekly=1,
        monthly=1,
    )
    assert config.times == "10:00,17:00"
    with pytest.raises(AppException):
        backups.update_settings(
            db_session,
            enabled=True,
            times="10:00",
            daily=0,
            weekly=1,
            monthly=1,
        )


def test_retention_preserves_independent_weeks_and_months(db_session, backup_storage):
    config = backups.get_settings(db_session)
    config.daily, config.weekly, config.monthly = 2, 3, 3
    newest = datetime(2026, 10, 2, tzinfo=UTC)
    entries = [
        make_backup(db_session, backup_storage, when=newest - timedelta(days=n))
        for n in (0, 1, 2, 8, 15, 30, 60, 90)
    ]
    keep = backups.retention_ids(entries, config)
    assert {entries[n].id for n in (0, 1, 2, 3, 4, 6)} == keep
    backups.apply_retention(db_session, backup_storage, config)
    for backup in entries:
        assert backup_storage.path(backup.id).exists() == (backup.id in keep)
        assert backup.status == ("success" if backup.id in keep else "expired")


def test_failed_creation_preserves_only_usable_backup_and_sanitizes_errors(
    db_session, backup_storage, caplog
):
    previous = make_backup(db_session, backup_storage)
    config = backups.get_settings(db_session)
    queued = backups.enqueue(db_session)

    def fail(*args):
        raise RuntimeError("postgres://user:SECRET@example/private")

    backups.execute_backup(
        db_session, queued, backup_storage, config, archive_factory=fail
    )
    assert queued.status == "failed"
    assert backup_storage.available(previous)
    assert "SECRET" not in (queued.error + caplog.text)


def test_local_path_validation_and_symlinks(backup_storage, tmp_path):
    for identifier in ("../secret", "A" * 32, "0" * 31):
        with pytest.raises(AppException):
            backup_storage.path(identifier)
    identifier = uuid4().hex
    (backup_storage.root / f"{identifier}.absbackup").symlink_to(tmp_path / "secret")
    with pytest.raises(AppException):
        backup_storage.path(identifier)
    assert backup_storage.root.stat().st_mode & 0o777 == 0o700


def test_pg_dump_uses_custom_format_snapshot_timeout_and_no_password_argument(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+psycopg2://user:SECRET@db:5432/attendance?sslmode=require",
    )
    called = {}

    def run(args, **kwargs):
        called.update(args=args, **kwargs)
        tmp_path.joinpath("dump").write_bytes(b"PGDMP")

    monkeypatch.setattr(subprocess, "run", run)
    backups.dump_database(tmp_path / "dump", "00000003-00000002-1")
    assert "-Fc" in called["args"]
    assert "SECRET" not in repr(called["args"])
    assert called["env"]["PGPASSWORD"] == "SECRET"
    assert called["env"]["PGSSLMODE"] == "require"
    assert called["timeout"] == settings.backup_timeout_seconds
    assert called["stderr"] == subprocess.DEVNULL


def test_archive_contains_database_photos_and_manifest(
    engine, backup_storage, monkeypatch, tmp_path
):
    photo = tmp_path / "photos" / "sample.jpg"
    photo.write_bytes(b"photo")
    monkeypatch.setattr(
        backups, "dump_database", lambda path, snapshot: path.write_bytes(b"PGDMP mock")
    )
    backup = SimpleNamespace(id=uuid4().hex, created_at=datetime.now(UTC))
    path = backups.create_archive(backup, backup_storage, engine)
    assert path.stat().st_mode & 0o777 == 0o600
    plaintext = tmp_path / "archive.tar"
    decrypt_archive(path, plaintext, encryption_key())
    with tarfile.open(plaintext) as archive:
        assert {"database.dump", "photos/sample.jpg", "manifest.json"} <= set(
            archive.getnames()
        )
        assert archive.extractfile("photos/sample.jpg").read() == b"photo"
    assert not list(backup_storage.root.glob(".*"))
    photo.unlink()
    photo.symlink_to(tmp_path / "secret")
    backup.id = uuid4().hex
    with pytest.raises(ValueError):
        backups.create_archive(backup, backup_storage, engine)
    assert not backup_storage.path(backup.id).exists()
    assert not list(backup_storage.root.glob(".*"))


def test_service_endpoints_require_admin_and_csrf(client, backup_storage):
    for path in ("/admin/backups/api", f"/admin/backups/{uuid4().hex}/download"):
        assert client.get(path, follow_redirects=False).status_code == 303
    assert (
        client.post(
            "/admin/backups/api", headers={"Origin": "https://attacker.test"}
        ).status_code
        == 403
    )
    assert client.post("/admin/backups/api", follow_redirects=False).status_code == 303


def test_admin_queue_status_and_encrypted_download(
    client, authenticated_data_api, db_session, backup_storage
):
    response = client.post("/admin/backups/api")
    assert response.status_code == 202
    queued = db_session.get(Backup, response.json()["id"])
    assert queued.status == "queued"
    assert client.get(f"/admin/backups/{queued.id}/download").status_code == 404
    backups.execute_backup(
        db_session,
        queued,
        backup_storage,
        backups.get_settings(db_session),
        archive_factory=fake_archive,
    )
    inventory = client.get("/admin/backups/api").json()
    assert inventory[0]["local_available"]
    download = client.get(f"/admin/backups/{queued.id}/download")
    assert download.status_code == 200
    assert download.content == backup_storage.path(queued.id).read_bytes()
    assert "attachment" in download.headers["content-disposition"]
    assert client.get("/admin/backups/not-a-uuid/download").status_code == 422


def test_worker_schedule_deduplication_and_crash_recovery(
    engine, backup_storage, monkeypatch
):
    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    monkeypatch.setattr(backups, "create_archive", fake_archive)
    now = datetime(2026, 10, 2, 3, 0, tzinfo=UTC)
    try:
        assert backups.process_tick(engine, now=now) == "success"
        assert backups.process_tick(engine, now=now) == "idle"
        with Session(engine) as db:
            records = list(db.scalars(select(Backup)))
            assert len(records) == 1
            assert records[0].kind == "scheduled"
            config = db.get(BackupSettings, 1)
            config.enabled = False
            abandoned = make_backup(db, backup_storage, status="running")
            orphan = backup_storage.root / f".{abandoned.id}.work"
            orphan.mkdir()
            orphan.joinpath("database.dump").write_bytes(b"private")
            db.commit()
            abandoned_id, completed_id = abandoned.id, records[0].id
        assert backups.process_tick(engine, now=now) == "idle"
        with Session(engine) as db:
            failed = db.get(Backup, abandoned_id)
            assert failed.status == "failed"
            completed = db.get(Backup, completed_id)
            assert completed.status == "success"
            assert backup_storage.available(completed)
            assert not orphan.exists()
            assert db.get(BackupSettings, 1).worker_seen_at == now
    finally:
        with Session(engine) as db:
            db.execute(delete(Backup))
            db.execute(delete(BackupSettings))
            db.commit()


def test_decryption_does_not_delete_existing_staging_file(backup_storage, tmp_path):
    source = tmp_path / "archive"
    source.write_bytes(b"untrusted")
    destination = tmp_path / "plain.tar"
    staging = tmp_path / "plain.tar.partial"
    staging.write_bytes(b"existing work")
    with pytest.raises(FileExistsError):
        decrypt_archive(source, destination, encryption_key())
    assert staging.read_bytes() == b"existing work"


def test_successful_local_creation_and_retention_error(
    db_session, backup_storage, monkeypatch, caplog
):
    from pathlib import Path

    config = backups.get_settings(db_session)
    config.daily, config.weekly, config.monthly = 1, 0, 0
    previous = make_backup(
        db_session, backup_storage, when=datetime(2025, 1, 1, tzinfo=UTC)
    )
    old_path = backup_storage.path(previous.id)
    original_unlink = Path.unlink

    def fail_old_delete(path, *args, **kwargs):
        if path == old_path:
            raise PermissionError("SECRET")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_old_delete)
    queued = backups.enqueue(db_session)
    backups.execute_backup(
        db_session, queued, backup_storage, config, archive_factory=fake_archive
    )
    assert queued.status == "success" and queued.phase == "complete"
    assert queued.finished_at is not None
    assert backup_storage.available(queued)
    assert backup_storage.available(previous)
    assert previous.retention_error
    assert "SECRET" not in previous.retention_error + caplog.text


def test_daily_retention_counts_school_dates_instead_of_runs(backup_storage):
    config = SimpleNamespace(daily=2, weekly=0, monthly=0)
    dates = [
        datetime(2026, 10, 2, 10, tzinfo=UTC),
        datetime(2026, 10, 2, 3, tzinfo=UTC),
        datetime(2026, 10, 1, 18, tzinfo=UTC),  # Also October 2 in Jakarta.
        datetime(2026, 10, 1, 10, tzinfo=UTC),
        datetime(2026, 9, 30, 10, tzinfo=UTC),
    ]
    entries = [
        SimpleNamespace(id=str(i), created_at=d, status="success")
        for i, d in enumerate(dates)
    ]
    assert backups.retention_ids(entries, config) == {"0", "3"}


def test_damaged_archive_cannot_displace_healthy_recovery_point(
    db_session, backup_storage
):
    config = backups.get_settings(db_session)
    config.daily, config.weekly, config.monthly = 1, 0, 0
    healthy = make_backup(
        db_session, backup_storage, when=datetime(2025, 1, 1, tzinfo=UTC)
    )
    damaged = make_backup(db_session, backup_storage)
    path = backup_storage.path(damaged.id)
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    backups.apply_retention(db_session, backup_storage, config)
    assert backup_storage.available(healthy)
    assert path.exists() and damaged.integrity_error
    assert not backup_storage.available(damaged)
    assert healthy.retention_error is None


def test_unencrypted_factory_result_is_never_a_success(db_session, backup_storage):
    config = backups.get_settings(db_session)
    previous = make_backup(db_session, backup_storage)
    queued = backups.enqueue(db_session)

    def damaged(backup, storage, bind):
        path = storage.path(backup.id)
        path.write_bytes(b"incomplete archive")
        return path

    backups.execute_backup(
        db_session, queued, backup_storage, config, archive_factory=damaged
    )
    assert queued.status == "failed"
    assert backup_storage.available(previous)


@pytest.mark.parametrize("reference", ["photo", "logo"])
def test_missing_referenced_file_fails_creation(
    engine, backup_storage, monkeypatch, reference
):
    from app.models.student import Student
    from app.models.student_card import StudentCardSettings

    monkeypatch.setattr(
        backups, "dump_database", lambda path, snapshot: path.write_bytes(b"PGDMP mock")
    )
    with Session(engine) as db:
        if reference == "photo":
            record = Student(
                name="Missing backup photo", nisn="9999999999", photo_path="missing.jpg"
            )
            db.add(record)
            previous = None
        else:
            record = db.get(StudentCardSettings, 1)
            previous = record.logo_path
            record.logo_path = "missing.jpg"
        db.commit()
        try:
            backup = SimpleNamespace(id=uuid4().hex, created_at=datetime.now(UTC))
            with pytest.raises(ValueError, match="Referenced photo"):
                backups.create_archive(backup, backup_storage, engine)
            assert not backup_storage.path(backup.id).exists()
            assert not list(backup_storage.root.glob(".*"))
        finally:
            if reference == "photo":
                db.delete(record)
            else:
                record.logo_path = previous
            db.commit()


def test_worker_recovers_archive_published_before_success_commit(
    engine, backup_storage
):
    from sqlalchemy import delete

    try:
        with Session(engine) as db:
            config = backups.get_settings(db)
            config.enabled = False
            record = make_backup(db, backup_storage, status="running")
            fake_archive(record, backup_storage, None)
            identifier = record.id
            db.commit()
        assert backups.process_tick(engine) == "idle"
        with Session(engine) as db:
            record = db.get(Backup, identifier)
            assert record.status == "success" and record.error is None
            assert record.size == backup_storage.path(identifier).stat().st_size
    finally:
        with Session(engine) as db:
            db.execute(delete(Backup))
            db.execute(delete(BackupSettings))
            db.commit()


@pytest.mark.parametrize("state", ["failed", "busy"])
def test_one_shot_worker_exits_unsuccessfully(monkeypatch, state):
    import sys

    from app.jobs import backups as worker

    monkeypatch.setattr(sys, "argv", ["backups", "--once", "--manual"])
    monkeypatch.setattr(worker.os, "umask", lambda mask: None)
    monkeypatch.setattr(worker, "process_tick", lambda *args, **kwargs: state)
    with pytest.raises(SystemExit) as exc:
        worker.main()
    assert exc.value.code == 1


def test_manual_tick_bypasses_disabled_schedule(engine, backup_storage, monkeypatch):
    from sqlalchemy import delete

    monkeypatch.setattr(backups, "create_archive", fake_archive)
    try:
        with Session(engine) as db:
            config = backups.get_settings(db)
            config.enabled = False
            db.commit()
        assert backups.process_tick(engine, manual=True) == "success"
        with Session(engine) as db:
            record = db.scalar(select(Backup))
            assert record.kind == "manual" and record.slot is None
            assert backup_storage.available(record)
        assert backups.process_tick(engine) == "idle"
    finally:
        with Session(engine) as db:
            db.execute(delete(Backup))
            db.execute(delete(BackupSettings))
            db.commit()


@pytest.mark.skipif(
    os.environ.get("ABSENSA_TEST_REAL_BACKUP") != "1",
    reason="Opt in to a real PostgreSQL dump/restore drill; requires database creation privileges and PG18 clients.",
)
def test_real_encrypted_backup_restores_database_and_photos(
    engine, backup_storage, monkeypatch, tmp_path
):
    """Create a temporary destination database on the explicitly opted-in test server."""
    from app.models.scan_log import ScanLog
    from app.models.student import Student
    from app.models.student_card import StudentCardSettings

    assert shutil.which("pg_dump") and shutil.which("pg_restore")
    monkeypatch.setattr(
        settings, "database_url", engine.url.render_as_string(hide_password=False)
    )
    recovery_name = f"absensa_restore_{uuid4().hex}"
    recovery_url = engine.url.set(database=recovery_name)
    admin = engine.execution_options(isolation_level="AUTOCOMMIT")
    recovered = create_engine(recovery_url)
    photo_bytes, logo_bytes = b"recovery photo bytes", b"recovery logo bytes"
    Path(settings.photos_dir, "student.jpg").write_bytes(photo_bytes)
    Path(settings.photos_dir, "logo.jpg").write_bytes(logo_bytes)
    with Session(engine) as db:
        student = Student(
            name="Restore drill student", nisn="9999999998", photo_path="student.jpg"
        )
        db.add(student)
        db.flush()
        scan = ScanLog(
            student_id=student.id, name=student.name, timestamp=datetime.now(UTC)
        )
        db.add(scan)
        card = db.get(StudentCardSettings, 1)
        previous_logo = card.logo_path
        card.logo_path = "logo.jpg"
        db.commit()
        try:
            backup = SimpleNamespace(id=uuid4().hex, created_at=datetime.now(UTC))
            archive_path = backups.create_archive(backup, backup_storage, engine)
            verify_archive(archive_path, encryption_key())
            plaintext = tmp_path / "recovery.tar"
            decrypt_archive(archive_path, plaintext, encryption_key())
            extracted = tmp_path / "extracted"
            with tarfile.open(plaintext) as archive:
                archive.extractall(extracted, filter="data")
            manifest = json.loads((extracted / "manifest.json").read_text())
            assert manifest["id"] == backup.id
            assert manifest["schema_revision"]
            assert manifest["postgres_version"].startswith("18.")
            assert (extracted / "photos/student.jpg").read_bytes() == photo_bytes
            assert (extracted / "photos/logo.jpg").read_bytes() == logo_bytes
            with admin.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{recovery_name}"'))
            env = os.environ.copy()
            env.update(
                PGHOST=recovery_url.host,
                PGPORT=str(recovery_url.port),
                PGUSER=recovery_url.username,
                PGPASSWORD=recovery_url.password,
            )
            subprocess.run(
                [
                    "pg_restore",
                    "--no-password",
                    "--no-owner",
                    "--no-privileges",
                    "--single-transaction",
                    "--exit-on-error",
                    "-d",
                    recovery_name,
                    str(extracted / "database.dump"),
                ],
                env=env,
                check=True,
                capture_output=True,
                timeout=120,
            )
            with recovered.connect() as connection:
                assert (
                    connection.scalar(
                        text(
                            "SELECT photo_path FROM students WHERE nisn = '9999999998'"
                        )
                    )
                    == "student.jpg"
                )
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM scan_logs WHERE name = 'Restore drill student'"
                        )
                    )
                    == 1
                )
                assert (
                    connection.scalar(
                        text("SELECT logo_path FROM student_card_settings WHERE id = 1")
                    )
                    == "logo.jpg"
                )
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == manifest["schema_revision"]
                )
        finally:
            recovered.dispose()
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{recovery_name}"'))
            db.delete(scan)
            db.delete(student)
            card.logo_path = previous_logo
            db.commit()
