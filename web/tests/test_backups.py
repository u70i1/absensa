"""Backup service behavior uses a disposable database and mocked external tools."""

import base64
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
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
)
from app.services.exceptions import AppException
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr
from sqlalchemy import select, text


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
        storage.path(backup.id).write_bytes(b"usable archive")
    return backup


def fake_archive(backup, storage, bind):
    path = storage.path(backup.id)
    path.write_bytes(b"encrypted archive")
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
    assert decoded.read_bytes() == plaintext
    assert decoded.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        decrypt_archive(source, decoded, encryption_key())
    damaged = bytearray(source.read_bytes())
    damaged[100] ^= 1
    source.write_bytes(damaged)
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
    assert download.content == b"encrypted archive"
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
