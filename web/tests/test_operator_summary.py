"""Operator daily summary uses the local school day and active roster."""

import shutil
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.models.scan_log import ScanLog
from app.models.student import Student
from app.services import scan_service
from PIL import Image

from tests import test_access_auth
from tests.test_access_auth import device_login, operator_login

accounts = test_access_auth.accounts


def test_daily_summary_page_lists_absent_students_and_unique_attendees(
    client,
    accounts,
    db_session,
    existing_student,
    student_factory,
    scan_log_factory,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "photos_dir", str(tmp_path))
    absent = student_factory(
        name="Siswa Belum Hadir", class_id=existing_student.class_id, nisn="1000000021"
    )
    (tmp_path / "absent.jpg").write_bytes(b"photo")
    absent.photo_path = "absent.jpg"
    student_factory(name="Tanpa Kelas", nisn="1000000022")
    student_factory(name="Mantan Siswa", nisn="1000000023", current=False)
    scan_log_factory(existing_student)
    scan_log_factory(existing_student)  # Imported duplicate must count once.
    db_session.add(
        ScanLog(
            name="Siswa Dihapus", timestamp=datetime.now(ZoneInfo(settings.timezone))
        )
    )
    db_session.commit()

    device_login(client)
    operator_login(client, accounts[1][0])
    dashboard = client.get("/operator")
    assert '/operator/summary"' in dashboard.text
    assert "Ringkasan Hari Ini" in dashboard.text

    response = client.get("/operator/summary")
    assert response.status_code == 200
    assert "Ringkasan Harian" in response.text
    assert 'id="operator-absent-dialog"' in response.text
    assert response.text.count("data-absent-student") == 2
    assert (
        datetime.now(ZoneInfo(settings.timezone)).strftime("%d/%m/%Y") in response.text
    )
    assert "<strong>1</strong><span>Sudah hadir</span>" in response.text
    assert "<strong>2</strong><span>Belum hadir</span>" in response.text
    assert "Siswa Belum Hadir" in response.text
    assert "11B" in response.text
    assert "NISN 1000000021" in response.text
    assert f"/operator/students/{absent.id}/photo" in response.text
    assert "Tanpa Kelas" in response.text
    assert "Tanpa kelas" in response.text
    assert "NISN 1000000022" in response.text
    assert "Nicholas Angle" not in response.text
    assert "Mantan Siswa" not in response.text
    assert "Siswa Dihapus" not in response.text


def test_daily_summary_search_and_pagination(
    client, accounts, db_session, existing_student
):
    db_session.add_all(
        Student(name=f"Siswa {index:03d}", nisn=f"{2000000000 + index:010d}")
        for index in range(55)
    )
    db_session.commit()
    device_login(client)
    operator_login(client, accounts[1][0])

    first = client.get("/operator/summary")
    assert first.status_code == 200
    assert first.text.count("data-absent-student") == 50
    assert "<strong>56</strong><span>Belum hadir</span>" in first.text
    assert "Menampilkan 1–50 dari 56 siswa" in first.text
    assert "Siswa 048" in first.text
    assert "Siswa 049" not in first.text
    assert "page=2" in first.text

    second = client.get("/operator/summary?page=2")
    assert second.text.count("data-absent-student") == 6
    assert "Menampilkan 51–56 dari 56 siswa" in second.text
    assert "Siswa 049" in second.text and "Siswa 054" in second.text
    assert "Siswa 048" not in second.text

    searched = client.get("/operator/summary", params={"name": "sIsWa 050"})
    assert searched.status_code == 200
    assert searched.text.count("data-absent-student") == 1
    assert "Siswa 050" in searched.text
    assert "Nicholas Angle" not in searched.text
    assert "<strong>56</strong><span>Belum hadir</span>" in searched.text
    assert "Menampilkan 1–1 dari 1 siswa yang cocok" in searched.text

    filtered_page = client.get("/operator/summary", params={"name": "Siswa", "page": 2})
    assert filtered_page.text.count("data-absent-student") == 5
    assert "name=Siswa" in filtered_page.text
    assert "Menampilkan 51–55 dari 55 siswa yang cocok" in filtered_page.text

    empty = client.get("/operator/summary", params={"name": "%"})
    assert "Tidak ada siswa yang belum hadir dengan nama tersebut." in empty.text
    assert empty.text.count("data-absent-student") == 0
    assert "Menampilkan 0–0 dari 0 siswa yang cocok" in empty.text

    out_of_range = client.get("/operator/summary?page=999")
    assert "Menampilkan 51–56 dari 56 siswa" in out_of_range.text


def test_daily_summary_excludes_adjacent_local_days(
    db_session, existing_student, student_factory, scan_log_factory, monkeypatch
):
    monkeypatch.setattr(settings, "timezone", "Asia/Jakarta")
    local_tz = ZoneInfo("Asia/Jakarta")
    at = datetime(2026, 10, 6, 12, tzinfo=local_tz)
    yesterday = student_factory(name="Kemarin", nisn="1000000024")
    tomorrow = student_factory(name="Besok", nisn="1000000025")
    scan_log_factory(yesterday, datetime(2026, 10, 5, 23, 59, tzinfo=local_tz))
    scan_log_factory(tomorrow, datetime(2026, 10, 7, 0, 0, tzinfo=local_tz))
    scan_log_factory(existing_student, at - timedelta(hours=12))

    summary = scan_service.get_daily_summary(db_session, at)
    assert summary["summary_day"].isoformat() == "2026-10-06"
    assert summary["attended_count"] == 1
    assert {student.name for student in summary["absent_students"]} == {
        "Kemarin",
        "Besok",
    }


def test_daily_summary_requires_device_and_operator(client, accounts):
    assert (
        client.get("/operator/summary", follow_redirects=False)
        .headers["location"]
        .startswith("/trusteddevice/login")
    )
    device_login(client)
    assert (
        client.get("/operator/summary", follow_redirects=False)
        .headers["location"]
        .startswith("/operator/login")
    )
    operator_login(client, accounts[1][0])
    assert client.get("/operator/summary").status_code == 200


def test_daily_summary_dialog_shows_large_photo_and_restores_focus(
    client, accounts, db_session, existing_student, tmp_path, monkeypatch
):
    playwright = pytest.importorskip("playwright.sync_api")
    chromium = shutil.which("chromium")
    if not chromium:
        pytest.skip("Chromium is unavailable")
    monkeypatch.setattr(settings, "photos_dir", str(tmp_path))
    Image.new("RGB", (40, 40), "#219e95").save(tmp_path / "absent.jpg")
    existing_student.photo_path = "absent.jpg"
    db_session.commit()
    device_login(client)
    operator_login(client, accounts[1][0])

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=chromium)
        context = browser.new_context(viewport={"width": 1000, "height": 800})
        context.add_cookies(
            [
                {"name": name, "value": value, "url": "http://testserver"}
                for name, value in client.cookies.items()
            ]
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
        page.goto("http://testserver/operator/summary")
        entry = page.locator("[data-absent-student]")
        assert entry.locator("img").count() == 1
        entry.hover()
        page.wait_for_timeout(250)
        assert (
            entry.evaluate(
                "element => getComputedStyle(element.parentElement).transform"
            )
            != "none"
        )
        entry.click()
        dialog = page.locator("#operator-absent-dialog")
        assert dialog.is_visible()
        assert (
            dialog.evaluate("element => getComputedStyle(element).animationName")
            == "modal-open"
        )
        assert dialog.locator("h2").inner_text() == existing_student.name
        assert dialog.locator("img").count() == 1
        assert dialog.locator("img").evaluate("image => image.naturalWidth") == 40
        assert (
            dialog.locator(".operator-avatar").bounding_box()["width"]
            > entry.locator(".operator-avatar").bounding_box()["width"]
        )
        page.evaluate("""() => {
          window.operatorCloseAnimationSeen = false;
          const dialog = document.getElementById('operator-absent-dialog');
          new MutationObserver(() => {
            if (dialog.classList.contains('is-closing')) window.operatorCloseAnimationSeen = true;
          }).observe(dialog, { attributes: true, attributeFilter: ['class'] });
        }""")
        dialog.get_by_role("button", name="Tutup detail siswa").click()
        page.wait_for_function(
            "!document.getElementById('operator-absent-dialog').open"
        )
        assert page.evaluate("window.operatorCloseAnimationSeen")
        assert not dialog.is_visible()
        assert entry.evaluate("element => document.activeElement === element")
        entry.click()
        page.keyboard.press("Escape")
        page.wait_for_function(
            "!document.getElementById('operator-absent-dialog').open"
        )
        assert entry.evaluate("element => document.activeElement === element")
        assert not errors
        browser.close()
