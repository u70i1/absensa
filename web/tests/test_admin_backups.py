"""Admin backup pages, durable actions, validation and status fragments."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.admin_auth import ADMIN_SESSION_COOKIE
from app.core.config import settings
from app.models.admin import Admin
from app.models.backup import Backup
from app.routes.admin_backups import file_size, local_time
from app.services import backup_service as backups
from app.services.admin_auth_service import create_admin_session
from pydantic import SecretStr
from sqlalchemy import select

from tests.test_backups import fake_archive, make_backup


@pytest.fixture
def backup_admin(client, db_session, backup_storage):
    admin = Admin(username="backup-admin", password_hash="unused")
    db_session.add(admin)
    db_session.commit()
    client.cookies.set(
        ADMIN_SESSION_COOKIE, create_admin_session(db_session, admin, 1), path="/admin"
    )
    return client


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/admin/backups"),
        ("get", "/admin/backups/status"),
        ("get", "/admin/backups/confirm"),
        ("get", "/admin/backups/api"),
        ("post", "/admin/backups/manual"),
        ("post", "/admin/backups/settings"),
        ("post", "/admin/backups/api"),
        ("get", f"/admin/backups/{uuid4().hex}/download"),
    ],
)
def test_all_backup_routes_require_an_authenticated_administrator(client, method, path):
    response = getattr(client, method)(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    fragment = getattr(client, method)(
        path, headers={"HX-Request": "true"}, follow_redirects=False
    )
    assert fragment.status_code == 401
    assert fragment.headers["HX-Redirect"] == "/admin"


def test_inactive_admin_session_cannot_manage_backups(backup_admin, db_session):
    account = db_session.scalar(select(Admin).where(Admin.username == "backup-admin"))
    account.active = False
    db_session.commit()
    assert backup_admin.get("/admin/backups", follow_redirects=False).status_code == 303
    assert (
        backup_admin.post("/admin/backups/manual", follow_redirects=False).status_code
        == 303
    )


def test_empty_dashboard_uses_existing_layout_and_real_settings(backup_admin):
    page = backup_admin.get("/admin/backups")
    assert page.status_code == 200
    assert 'class="top-tab selected"' in page.text
    assert "Cadangan Data" in page.text
    assert "Belum ada cadangan" in page.text
    assert 'value="10:00"' in page.text and 'value="17:00"' in page.text
    assert "14 harian · 8 mingguan · 3 bulanan" in page.text
    assert "flashdisk atau hard disk eksternal" in page.text
    assert "S3" not in page.text
    assert 'hx-trigger="every 30s"' in page.text
    assert 'class="fluid-layout"' not in page.text
    assert page.headers["cache-control"] == "no-store"


def test_manual_confirmation_queue_poll_and_download(
    backup_admin, db_session, backup_storage
):
    confirm = backup_admin.get("/admin/backups/confirm", headers={"HX-Request": "true"})
    assert confirm.status_code == 200
    assert confirm.headers["X-Admin-Fragment"] == "modal"
    assert "Mulai cadangan" in confirm.text
    queued = backup_admin.post("/admin/backups/manual", follow_redirects=False)
    assert queued.status_code == 303
    assert "notice=queued" in queued.headers["location"]
    record = db_session.scalar(select(Backup))
    assert record.status == "queued"
    assert not backup_storage.path(record.id).exists()
    active = backup_admin.get("/admin/backups/status", headers={"HX-Request": "true"})
    assert "Dalam antrean" in active.text
    assert 'hx-trigger="every 5s"' in active.text
    assert "Menunggu pekerja cadangan" in active.text
    assert "<html" not in active.text
    assert (
        'name="time_one"' not in active.text
    )  # Polling cannot discard unsaved settings.
    backups.execute_backup(
        db_session,
        record,
        backup_storage,
        backups.get_settings(db_session),
        archive_factory=fake_archive,
    )
    complete = backup_admin.get("/admin/backups/status", headers={"HX-Request": "true"})
    assert "Berhasil" in complete.text
    assert f"/{record.id}/download" in complete.text
    assert 'hx-trigger="every 30s"' in complete.text
    assert (
        backup_admin.get(f"/admin/backups/{record.id}/download").content
        == backup_storage.path(record.id).read_bytes()
    )


def test_non_htmx_confirmation_and_status_fallback(backup_admin):
    standalone = backup_admin.get("/admin/backups/confirm")
    assert '<main class="standalone-dialog"' in standalone.text
    assert 'data-dashboard-home="/admin/backups"' in standalone.text
    status = backup_admin.get("/admin/backups/status?page=2", follow_redirects=False)
    assert status.status_code == 303
    assert status.headers["location"] == "/admin/backups?page=2"


def test_settings_save_and_reject_invalid_values_without_changing_configuration(
    backup_admin, db_session
):
    data = {
        "time_one": "08:30",
        "time_two": "16:45",
        "daily": 5,
        "weekly": 2,
        "monthly": 1,
        "enabled": "true",
    }
    result = backup_admin.post(
        "/admin/backups/settings", data=data, follow_redirects=False
    )
    assert result.status_code == 303
    config = backups.get_settings(db_session)
    assert (config.times, config.daily, config.weekly, config.monthly) == (
        "08:30,16:45",
        5,
        2,
        1,
    )
    invalid = backup_admin.post("/admin/backups/settings", data=data | {"daily": 0})
    assert invalid.status_code == 422
    assert "Retensi:" in invalid.text
    assert 'value="0"' in invalid.text
    assert backups.get_settings(db_session).daily == 5
    invalid_time = backup_admin.post(
        "/admin/backups/settings", data=data | {"time_one": "25:00"}
    )
    assert invalid_time.status_code == 422
    assert "HH:MM" in invalid_time.text
    assert backups.get_settings(db_session).times == "08:30,16:45"
    data.pop("enabled")
    data["time_two"] = ""
    assert backup_admin.post("/admin/backups/settings", data=data).status_code == 200
    assert not config.enabled
    assert config.times == "08:30"


def test_encryption_not_ready_and_worker_unavailable_are_clear(
    backup_admin, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "backup_encryption_key", SecretStr(""))
    page = backup_admin.get("/admin/backups")
    assert page.status_code == 200
    assert "Kunci belum siap" in page.text
    assert "Layanan cadangan belum melaporkan" in page.text
    assert backup_admin.post("/admin/backups/manual").status_code == 503
    modal = backup_admin.get("/admin/backups/confirm", headers={"HX-Request": "true"})
    assert modal.status_code == 503
    assert modal.headers["X-Admin-Fragment"] == "modal"
    assert "Cadangan belum siap" in modal.text
    assert db_session.scalar(select(Backup)) is None


def test_failed_attempt_keeps_the_previous_recovery_point(
    backup_admin, db_session, backup_storage
):
    usable = make_backup(db_session, backup_storage)
    usable.size = 1024 * 1024
    failed = make_backup(db_session, backup_storage, status="failed")
    failed.error = "Ruang disk tidak tersedia."
    db_session.commit()
    page = backup_admin.get("/admin/backups")
    assert failed.error in page.text
    assert "1.0 MiB" in page.text
    assert f"/{usable.id}/download" in page.text
    assert f"/{failed.id}/download" not in page.text
    backup_storage.path(usable.id).unlink()
    missing = backup_admin.get("/admin/backups")
    assert f"/{usable.id}/download" not in missing.text
    assert backup_admin.get(f"/admin/backups/{usable.id}/download").status_code == 404


def test_creation_progress_and_fresh_worker_status(
    backup_admin, db_session, backup_storage
):
    record = make_backup(db_session, backup_storage)
    record.status, record.phase = "running", "archiving"
    config = backups.get_settings(db_session)
    config.worker_seen_at = datetime.now(UTC) - timedelta(minutes=3)
    db_session.commit()
    page = backup_admin.get("/admin/backups")
    assert "Menyalin database dan berkas" in page.text
    assert "Sedang diproses…" in page.text
    assert 'hx-trigger="every 5s"' in page.text
    assert "Layanan cadangan belum melaporkan" not in page.text
    assert f"/{record.id}/download" not in page.text


def test_pagination_and_local_timezone(backup_admin, db_session, backup_storage):
    oldest = datetime(2026, 10, 1, 17, 15, tzinfo=UTC)
    ids = []
    for index in range(26):
        row = make_backup(
            db_session,
            backup_storage,
            when=oldest + timedelta(minutes=index),
            status="failed",
        )
        ids.append(row.id)
    first = backup_admin.get("/admin/backups")
    assert first.text.count("data-backup-id=") == 25
    assert ids[0] not in first.text
    second = backup_admin.get("/admin/backups?page=2", headers={"HX-Request": "true"})
    assert second.text.count("data-backup-id=") == 1
    assert ids[0] in second.text
    assert "02/10/2026 00:15:00" in second.text
    assert second.headers["HX-Push-Url"] == "/admin/backups?page=2"
    assert backup_admin.get("/admin/backups?page=-1").status_code == 422
    assert backup_admin.get("/admin/backups?page=999999").status_code == 200
    assert local_time(oldest) == "02/10/2026 00:15:00"
    assert file_size(None) == "—" and file_size(500) == "500 B"


@pytest.mark.parametrize("path", ["/admin/backups/manual", "/admin/backups/settings"])
def test_backup_ui_mutations_reject_cross_origin_and_missing_origin(backup_admin, path):
    for origin in ("https://attacker.test", ""):
        assert backup_admin.post(path, headers={"Origin": origin}).status_code == 403


def test_error_content_is_escaped(backup_admin, db_session, backup_storage):
    record = make_backup(db_session, backup_storage, status="failed")
    record.error = "<script>alert('private')</script>"
    db_session.commit()
    page = backup_admin.get("/admin/backups")
    assert "<script>alert" not in page.text
    assert "&lt;script&gt;alert" in page.text


def test_local_backup_page_does_not_expose_encryption_key(backup_admin):
    page = backup_admin.get("/admin/backups")
    assert settings.backup_encryption_key.get_secret_value() not in page.text
    assert "BACKUP_S3" not in page.text
    assert "Simpan salinan di flashdisk" in page.text


def test_damaged_backup_is_excluded_from_recovery_summary_and_download(
    backup_admin, db_session, backup_storage
):
    healthy = make_backup(
        db_session, backup_storage, when=datetime.now(UTC) - timedelta(days=2)
    )
    damaged = make_backup(db_session, backup_storage)
    backup_storage.path(damaged.id).write_bytes(b"damaged archive")
    backups.apply_retention(
        db_session, backup_storage, backups.get_settings(db_session)
    )
    page = backup_admin.get("/admin/backups")
    assert "Arsip tidak dapat diverifikasi" in page.text
    assert "lebih dari 24 jam" in page.text
    assert f"/{healthy.id}/download" in page.text
    assert f"/{damaged.id}/download" not in page.text
    assert backup_admin.get(f"/admin/backups/{damaged.id}/download").status_code == 404
