"""Database-backed jobs executed by a dedicated worker, never HTTP tasks."""

import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.backup import Backup, BackupSettings
from app.services.backup_crypto_service import (
    EncryptedWriter,
    encryption_key,
    verify_archive,
)
from app.services.backup_storage_service import LocalBackupStorage
from app.services.exceptions import AppException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
LOCK_ID = 418527091
ACTIVE = ("queued", "running")


def normalize_times(value: str) -> str:
    times = value.split(",")
    if not 1 <= len(times) <= 2 or any(
        not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in times
    ):
        raise AppException("Isi satu atau dua waktu HH:MM, dipisahkan koma.", 422)
    return ",".join(sorted(set(times)))


def get_settings(db: Session) -> BackupSettings:
    config = db.get(BackupSettings, 1)
    if config is None:
        db.execute(
            insert(BackupSettings)
            .values(
                id=1,
                enabled=True,
                times=normalize_times(settings.backup_times),
                daily=settings.backup_keep_daily,
                weekly=settings.backup_keep_weekly,
                monthly=settings.backup_keep_monthly,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        db.commit()
        config = db.get(BackupSettings, 1)
    return config


def update_settings(
    db: Session,
    *,
    enabled: bool,
    times: str,
    daily: int,
    weekly: int,
    monthly: int,
) -> BackupSettings:
    times = normalize_times(times)
    if not (1 <= daily <= 365 and 0 <= weekly <= 104 and 0 <= monthly <= 120):
        raise AppException("Retensi: harian 1–365, mingguan 0–104, bulanan 0–120.", 422)
    config = get_settings(db)
    config.enabled, config.times = enabled, times
    config.daily, config.weekly, config.monthly = daily, weekly, monthly
    db.commit()
    return config


def active_backup(db: Session) -> Backup | None:
    return db.scalar(select(Backup).where(Backup.status.in_(ACTIVE)))


def enqueue(
    db: Session, *, slot: str | None = None, now: datetime | None = None
) -> Backup:
    encryption_key()  # Fail early without persisting an unusable manual request.
    # Serialize HTTP requests with each other and with the worker's session lock.
    locked = db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_ID})
    active = active_backup(db)
    if active:
        return active
    if not locked:
        raise AppException("Pekerja cadangan sedang sibuk. Coba lagi sebentar.", 409)
    if slot:
        existing = db.scalar(select(Backup).where(Backup.slot == slot))
        if existing:
            return existing
    backup = Backup(
        id=uuid4().hex,
        created_at=now or datetime.now(UTC),
        kind="scheduled" if slot else "manual",
        slot=slot,
        status="queued",
        phase="queued",
    )
    db.add(backup)
    db.commit()
    return backup


def due_slot(config: BackupSettings, now: datetime) -> str | None:
    if not config.enabled:
        return None
    local = now.astimezone(ZoneInfo(settings.timezone))
    due = [t for t in config.times.split(",") if t <= local.strftime("%H:%M")]
    # Catch up the latest slot today after downtime, without replaying old days.
    return f"{local.date().isoformat()}T{max(due)}@{settings.timezone}" if due else None


def retention_ids(backups: list[Backup], config: BackupSettings) -> set[str]:
    """Union of newest representatives per school-local date, week and month."""
    successful = sorted(
        (b for b in backups if b.status == "success"),
        key=lambda b: b.created_at,
        reverse=True,
    )
    keep = set()
    days, weeks, months = set(), set(), set()
    for backup in successful:
        local = backup.created_at.astimezone(ZoneInfo(settings.timezone))
        week = local.isocalendar()[:2]
        month = (local.year, local.month)
        day = local.date()
        if day not in days and len(days) < config.daily:
            days.add(day)
            keep.add(backup.id)
        if week not in weeks and len(weeks) < config.weekly:
            weeks.add(week)
            keep.add(backup.id)
        if month not in months and len(months) < config.monthly:
            months.add(month)
            keep.add(backup.id)
    return keep


def apply_retention(
    db: Session, storage: LocalBackupStorage, config: BackupSettings
) -> None:
    backups = list(db.scalars(select(Backup).where(Backup.status == "success")))
    # Damaged archives must never displace a healthy recovery point. Keep them
    # for investigation (including archives encrypted with a previous key).
    key = encryption_key()
    usable = []
    for backup in backups:
        try:
            if not storage.present(backup):
                raise ValueError("Archive unavailable")
            verify_archive(storage.path(backup.id), key)
            usable.append(backup)
            backup.integrity_error = None
            backup.retention_error = None
        except Exception:  # noqa: BLE001 - sanitized integrity/storage error
            backup.integrity_error = "Arsip tidak dapat diverifikasi. Periksa media penyimpanan dan kunci pemulihan; arsip dipertahankan."
    keep = retention_ids(usable, config)
    if not keep:
        db.commit()
        return
    for backup in usable:
        if backup.id in keep:
            continue
        try:
            storage.path(backup.id).unlink(missing_ok=True)
            backup.status, backup.phase = "expired", "expired"
            backup.retention_error = None
        except Exception:  # noqa: BLE001 - sanitize arbitrary SDK/tool failures
            # Keep the recovery point if deletion fails and try on next success.
            backup.retention_error = "Rotasi cadangan gagal. Periksa izin folder dan sambungan media penyimpanan."
            logger.warning("Backup retention failed: %s", backup.id)
    db.commit()


def dump_database(destination: Path, snapshot: str) -> None:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL required")
    env = os.environ.copy()
    # libpq environment avoids credentials in process arguments or exceptions.
    env.update(
        PGHOST=url.host or "localhost",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
        PGDATABASE=url.database or "",
        PGCONNECT_TIMEOUT="10",
    )
    for option in ("sslmode", "sslcert", "sslkey", "sslrootcert"):
        if option in url.query:
            env[f"PG{option.upper()}"] = url.query[option]
    subprocess.run(
        [
            "pg_dump",
            "-Fc",
            "--no-password",
            f"--snapshot={snapshot}",
            "--file",
            str(destination),
        ],
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=settings.backup_timeout_seconds,
    )
    os.chmod(destination, 0o600)


def create_archive(backup: Backup, storage: LocalBackupStorage, bind) -> Path:
    """Pin the DB snapshot and block photo writers while copying associated files."""
    key = encryption_key()
    storage.prepare()
    staging = storage.root / f".{backup.id}.work"
    partial = storage.root / f".{backup.id}.partial"
    staging.mkdir(mode=0o700)
    destination = storage.path(backup.id)
    try:
        with bind.connect() as connection, connection.begin():
            # Writers store files before committing and delete old files afterward.
            # These locks protect referenced photos/logos during snapshot capture.
            connection.execute(text("SET LOCAL lock_timeout = '30s'"))
            connection.execute(
                text("LOCK TABLE students, student_card_settings IN SHARE MODE")
            )
            snapshot = connection.scalar(text("SELECT pg_export_snapshot()"))
            # The locked tables cannot change between snapshot export and this
            # inventory. A missing referenced file must fail the entire job.
            required_photos = set(
                connection.scalars(
                    text(
                        "SELECT photo_path FROM students WHERE photo_path IS NOT NULL "
                        "UNION SELECT logo_path FROM student_card_settings WHERE logo_path IS NOT NULL"
                    )
                )
            )
            dump_database(staging / "database.dump", snapshot)
            with (staging / "database.dump").open("rb") as dump:
                if dump.read(5) != b"PGDMP":
                    raise ValueError("Invalid database dump")
            with partial.open("xb") as output:
                os.chmod(partial, 0o600)
                encrypted = EncryptedWriter(output, key)
                with tarfile.open(fileobj=encrypted, mode="w|") as archive:
                    archive.add(
                        staging / "database.dump",
                        arcname="database.dump",
                        recursive=False,
                    )
                    photos = Path(settings.photos_dir).absolute()
                    if photos.is_symlink() or not photos.is_dir():
                        raise ValueError("Photo volume missing")
                    for filename in required_photos:
                        if (
                            Path(filename).name != filename
                            or (photos / filename).is_symlink()
                            or not (photos / filename).is_file()
                        ):
                            raise ValueError("Referenced photo missing or unsafe")
                    archive.add(photos, arcname="photos", recursive=False)
                    copied_photos = set()
                    for path in sorted(photos.rglob("*")):
                        if path.is_symlink() or not (path.is_file() or path.is_dir()):
                            raise ValueError("Unsupported photo entry")
                        archive.add(
                            path,
                            arcname=str(Path("photos") / path.relative_to(photos)),
                            recursive=False,
                        )
                        if path.is_file():
                            copied_photos.add(str(path.relative_to(photos)))
                    if not required_photos <= copied_photos:
                        raise ValueError("Referenced photo disappeared")
                    manifest = staging / "manifest.json"
                    manifest.write_text(
                        json.dumps(
                            {
                                "version": 1,
                                "id": backup.id,
                                "created_at": backup.created_at.isoformat(),
                                "format": "pg_dump -Fc",
                                "files": "photos",
                                "schema_revision": connection.scalar(
                                    text("SELECT version_num FROM alembic_version")
                                ),
                                "postgres_version": connection.scalar(
                                    text("SHOW server_version")
                                ),
                            }
                        )
                    )
                    archive.add(manifest, arcname="manifest.json", recursive=False)
                encrypted.finish()
        os.replace(partial, destination)
        # Persist the directory entry before advertising the archive as complete.
        fd = os.open(storage.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return destination
    finally:
        partial.unlink(missing_ok=True)
        shutil.rmtree(staging)


def execute_backup(
    db: Session,
    backup: Backup,
    storage: LocalBackupStorage,
    config: BackupSettings,
    *,
    archive_factory=create_archive,
) -> None:
    backup.status, backup.phase = "running", "archiving"
    db.commit()
    try:
        path = archive_factory(backup, storage, db.get_bind())
        # Read back the encrypted file from storage before advertising success.
        verify_archive(path, encryption_key())
        backup.size = path.stat().st_size
        backup.status, backup.phase = "success", "complete"
        backup.finished_at = datetime.now(UTC)
        db.commit()
        logger.info("Backup completed: %s", backup.id)
    except Exception:  # noqa: BLE001 - sanitize arbitrary tool failures
        db.rollback()
        backup.status, backup.phase = "failed", "failed"
        backup.error = "Pembuatan cadangan gagal. Periksa ruang disk, izin folder, kunci enkripsi, dan koneksi database."
        backup.finished_at = datetime.now(UTC)
        db.commit()
        logger.warning("Backup creation failed: %s", backup.id)
        return
    apply_retention(db, storage, config)


def process_tick(
    bind, *, now: datetime | None = None, manual: bool = False, progress=None
) -> str:
    """Hold a cross-process PostgreSQL session lock for recovery and execution."""
    now = now or datetime.now(UTC)
    with bind.connect() as lock_connection:
        acquired = lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_ID}
        )
        lock_connection.commit()
        if not acquired:
            return "busy"
        try:
            with Session(bind=lock_connection) as db:
                config = get_settings(db)
                config.worker_seen_at = now
                storage = LocalBackupStorage()
                storage.prepare()
                # Owning this lock proves any earlier execution no longer owns it.
                for interrupted in db.scalars(
                    select(Backup).where(Backup.status == "running")
                ):
                    try:
                        path = storage.path(interrupted.id)
                        verify_archive(path, encryption_key())
                    except Exception:  # noqa: BLE001 - sanitized recovery error
                        interrupted.status, interrupted.phase = "failed", "failed"
                        interrupted.error = (
                            "Pekerja cadangan terhenti. Jalankan cadangan baru."
                        )
                    else:
                        # Publication can finish just before a crash prevents the
                        # success transaction. Recover that complete local copy.
                        interrupted.size = path.stat().st_size
                        interrupted.status, interrupted.phase = "success", "complete"
                        interrupted.error = None
                    interrupted.finished_at = now
                db.commit()
                if progress is not None:
                    progress()
                # Only clean this service's UUID-shaped temporary files under lock.
                for path in storage.root.iterdir():
                    if re.fullmatch(r"\.[0-9a-f]{32}\.(work|partial)", path.name):
                        if path.is_dir() and not path.is_symlink():
                            shutil.rmtree(path)
                        else:
                            path.unlink()
                backup = active_backup(db)
                if backup is None:
                    slot = None if manual else due_slot(config, now)
                    if manual or (
                        slot
                        and not db.scalar(select(Backup.id).where(Backup.slot == slot))
                    ):
                        backup = enqueue(db, slot=slot, now=now)
                if backup is None:
                    return "idle"
                # Use the Engine for the independent exported-snapshot connection.
                execute_backup(
                    db,
                    backup,
                    storage,
                    config,
                    archive_factory=lambda b, s, _: create_archive(b, s, bind),
                )
                return backup.status
        finally:
            lock_connection.rollback()
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID}
            )
            lock_connection.commit()
