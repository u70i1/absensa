"""Chromium checks using the existing TestClient interception pattern."""

import shutil
from urllib.parse import urlsplit

import pytest
from app.models.backup import Backup
from app.services import backup_service as backups
from sqlalchemy import select

from tests.test_backups import fake_archive

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def backup_browser(client, authenticated_data_api, backup_storage):
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=shutil.which("chromium"))
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100}, accept_downloads=True
        )

        def serve(route):
            request = route.request
            url = urlsplit(request.url)
            response = client.request(
                request.method,
                url.path + ("?" + url.query if url.query else ""),
                content=request.post_data_buffer,
                headers={**request.headers, "origin": "http://testserver"},
                follow_redirects=False,
            )
            route.fulfill(
                status=response.status_code,
                headers=dict(response.headers),
                body=response.content,
            )

        context.route("http://testserver/**", serve)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page, context
        assert not errors
        browser.close()


def test_backup_confirmation_queue_progress_download_and_settings(
    backup_browser, db_session, backup_storage, tmp_path
):
    page, _ = backup_browser
    expect = playwright.expect
    page.goto("http://testserver/admin/backups")
    expect(page.get_by_role("heading", name="Cadangan Data")).to_be_visible()
    assert (
        page.locator("body").evaluate("body => getComputedStyle(body).minWidth")
        == "1100px"
    )
    page.get_by_role("link", name="Buat cadangan", exact=True).click()
    expect(page.locator("#student-modal")).to_be_visible()
    expect(page.get_by_role("heading", name="Buat cadangan sekarang?")).to_be_visible()
    page.get_by_role("button", name="Batal", exact=True).click()
    expect(page.locator("#student-modal")).not_to_be_visible()
    assert db_session.scalar(select(Backup)) is None
    page.get_by_role("link", name="Buat cadangan", exact=True).click()
    page.get_by_role("button", name="Mulai cadangan", exact=True).click()
    expect(
        page.get_by_text("Cadangan masuk antrean. Status diperbarui otomatis.")
    ).to_be_visible()
    expect(page.get_by_role("button", name="Menunggu antrean…")).to_be_disabled()
    record = db_session.scalar(select(Backup))
    assert record.status == "queued"
    assert not backup_storage.path(record.id).exists()

    # Editing the form survives the same HTMX fragment request used by polling.
    page.locator("#backup-daily").fill("5")
    record.status, record.phase = "running", "archiving"
    db_session.commit()
    page.get_by_role("link", name="Perbarui status").click()
    expect(page.get_by_role("button", name="Sedang diproses…")).to_be_disabled()
    expect(page.locator("#backup-daily")).to_have_value("5")
    backups.execute_backup(
        db_session,
        record,
        backup_storage,
        backups.get_settings(db_session),
        archive_factory=fake_archive,
    )
    page.get_by_role("link", name="Perbarui status").click()
    expect(page.get_by_role("link", name="Unduh", exact=True)).to_be_visible()
    with page.expect_download() as event:
        page.get_by_role("link", name="Unduh", exact=True).click()
    download = event.value
    assert download.suggested_filename.endswith(".absbackup")
    destination = tmp_path / "download.absbackup"
    download.save_as(destination)
    assert destination.read_bytes() == backup_storage.path(record.id).read_bytes()

    page.locator("#backup-time-one").fill("08:30")
    page.locator("#backup-time-two").fill("16:45")
    page.locator("#backup-weekly").fill("2")
    page.locator("#backup-monthly").fill("1")
    page.get_by_role("button", name="Simpan pengaturan").click()
    expect(page.get_by_text("Pengaturan cadangan disimpan.")).to_be_visible()
    config = backups.get_settings(db_session)
    assert (config.times, config.daily, config.weekly, config.monthly) == (
        "08:30,16:45",
        5,
        2,
        1,
    )
    page.screenshot(path="/tmp/absensa-backup-admin.png", full_page=True)
    assert page.locator("body").evaluate(
        "body => body.scrollWidth <= window.innerWidth"
    )


def test_backup_polling_runs_without_an_admin_click(
    backup_browser, db_session, backup_storage
):
    page, _ = backup_browser
    page.goto("http://testserver/admin/backups")
    record = backups.enqueue(db_session)
    page.reload()
    playwright.expect(
        page.get_by_role("button", name="Menunggu antrean…")
    ).to_be_disabled()
    backups.execute_backup(
        db_session,
        record,
        backup_storage,
        backups.get_settings(db_session),
        archive_factory=fake_archive,
    )
    with page.expect_response("**/backups/status?page=1", timeout=10000):
        pass
    playwright.expect(
        page.get_by_role("link", name="Unduh", exact=True)
    ).to_be_visible()
    playwright.expect(
        page.get_by_role("link", name="Buat cadangan", exact=True)
    ).to_be_visible()
