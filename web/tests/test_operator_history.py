"""Scanner history, stable older-record loading, and the public entry point."""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.scan_log import ScanLog
from app.services import scan_service

from tests.test_access_auth import accounts, device_login, operator_login  # noqa: F401


def test_root_is_public_without_redirect(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "location" not in response.headers and "HX-Redirect" not in response.headers
    assert "Buka presensi" in response.text and "Dashboard admin" in response.text


def test_older_history_endpoint_remains_stable(
    client, accounts, db_session, existing_student, monkeypatch
):
    monkeypatch.setattr(settings, "timezone", "Asia/Jakarta")
    start = datetime(2026, 9, 23, 6, tzinfo=timezone.utc)
    scans = [
        ScanLog(
            student_id=existing_student.id,
            name=f"History {i}",
            class_name="10A",
            timestamp=start - timedelta(minutes=i),
        )
        for i in range(35)
    ]
    db_session.add_all(scans)
    db_session.commit()
    device_login(client)
    operator_login(client, accounts[1][0])
    page = client.get("/operator")
    assert "Riwayat Scan Hari Ini" in page.text
    assert "Belum ada presensi hari ini" in page.text
    first_page = client.get("/operator/history", headers={"HX-Request": "true"})
    ids = [int(value) for value in re.findall(r'data-scan-id="(\d+)"', first_page.text)]
    assert ids == [scan.scan_id for scan in scans[:30]]
    assert "13:00:00" in first_page.text  # Asia/Jakarta, UTC+7.
    assert "Muat riwayat sebelumnya" in first_page.text
    cursor = scans[29].scan_id
    # A newly inserted scan must not shift the second page or repeat old rows.
    db_session.add(
        ScanLog(
            student_id=existing_student.id,
            name="New arrival",
            timestamp=start + timedelta(minutes=1),
        )
    )
    db_session.commit()
    fragment = client.get(
        f"/operator/history?before={cursor}", headers={"HX-Request": "true"}
    )
    assert [
        int(value) for value in re.findall(r'data-scan-id="(\d+)"', fragment.text)
    ] == [scan.scan_id for scan in scans[30:]]
    assert "Muat riwayat sebelumnya" not in fragment.text
    fallback = client.get(f"/operator?before={cursor}")
    assert fallback.status_code == 200 and "Riwayat Scan Hari Ini" in fallback.text
    assert (
        client.get(
            f"/operator/history?before={cursor}", follow_redirects=False
        ).headers["location"]
        == f"/operator?before={cursor}"
    )


def test_history_ties_use_id_and_preserve_deleted_student_snapshots(db_session):
    timestamp = datetime(2026, 9, 23, tzinfo=timezone.utc)
    scans = [
        ScanLog(name=f"Snapshot {i}", class_name="10A", timestamp=timestamp)
        for i in range(3)
    ]
    db_session.add_all(scans)
    db_session.commit()
    first = scan_service.get_recent_history(db_session, limit=2)
    assert [row.scan_id for row in first["history"]] == [
        scans[2].scan_id,
        scans[1].scan_id,
    ]
    second = scan_service.get_recent_history(db_session, before=first["next_cursor"])
    assert second["history"][0].name == "Snapshot 0"
    assert second["history"][0].nisn is None


def test_scan_refreshes_history_and_errors_keep_input(
    client, accounts, existing_student
):
    device_login(client)
    operator_login(client, accounts[1][0])
    assert "Belum ada presensi hari ini" in client.get("/operator").text
    response = client.post(
        "/operator/scans",
        data={"nisn": existing_student.nisn},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200 and 'id="scan-feedback"' in response.text
    assert 'data-scan-succeeded="true"' in response.text
    assert 'data-scan-card' in response.text
    recent = client.get("/operator/recent", headers={"HX-Request": "true"})
    assert len(re.findall(r'data-scan-id="', recent.text)) == 1
    duplicate = client.post("/operator/scans", data={"nisn": existing_student.nisn})
    assert duplicate.status_code == 409
    assert f'value="{existing_student.nisn}"' in duplicate.text
    assert len(re.findall(r'data-scan-id="', duplicate.text)) == 1


def test_recent_history_is_today_only_global_and_capped_at_25(
    client, accounts, db_session, existing_student
):
    local_tz = ZoneInfo(settings.timezone)
    today = datetime.now(local_tz).replace(hour=8, minute=0, second=0, microsecond=0)
    scans = [
        ScanLog(
            student_id=existing_student.id,
            name=f"Siswa {index}",
            timestamp=today + timedelta(seconds=index),
        )
        for index in range(27)
    ]
    scans.append(ScanLog(name="Kemarin", timestamp=today - timedelta(days=1)))
    db_session.add_all(scans)
    db_session.commit()
    device_login(client)
    operator_login(client, accounts[1][0])
    page = client.get("/operator")
    ids = [int(value) for value in re.findall(r'data-scan-id="(\d+)"', page.text)]
    assert ids == [scan.scan_id for scan in reversed(scans[:27])][:25]
    assert "27 siswa tercatat hari ini" in page.text
    assert "Kemarin" not in page.text

    db_session.add(
        ScanLog(name="Dari perangkat lain", timestamp=today + timedelta(minutes=1))
    )
    db_session.commit()
    refreshed = client.get("/operator/recent", headers={"HX-Request": "true"})
    assert refreshed.status_code == 200
    assert "Dari perangkat lain" in refreshed.text
    assert "28 siswa tercatat hari ini" in refreshed.text
    assert len(re.findall(r'data-scan-id="', refreshed.text)) == 25


def test_history_requires_both_authentication_layers(client, accounts):
    assert (
        client.get("/operator/history", follow_redirects=False)
        .headers["location"]
        .startswith("/trusteddevice/login")
    )
    device_login(client)
    assert (
        client.get("/operator/history", follow_redirects=False)
        .headers["location"]
        .startswith("/operator/login")
    )
    operator_login(client, accounts[1][0])
    assert client.get("/operator/history?before=0").status_code == 422
    assert (
        client.get(
            "/operator/history?before=2147483647", headers={"HX-Request": "true"}
        ).status_code
        == 404
    )


def test_operator_photo_route_requires_both_layers(
    client, accounts, db_session, existing_student, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "photos_dir", str(tmp_path))
    (tmp_path / "portrait.jpg").write_bytes(b"portrait")
    existing_student.photo_path = "portrait.jpg"
    db_session.commit()
    path = f"/operator/students/{existing_student.id}/photo"
    assert client.get(path, follow_redirects=False).headers["location"].startswith(
        "/trusteddevice/login"
    )
    device_login(client)
    assert client.get(path, follow_redirects=False).headers["location"].startswith(
        "/operator/login"
    )
    operator_login(client, accounts[1][0])
    response = client.get(path)
    assert response.status_code == 200
    assert response.content == b"portrait"
    scanned = client.post("/operator/scans", data={"nisn": existing_student.nisn})
    assert path in scanned.text
