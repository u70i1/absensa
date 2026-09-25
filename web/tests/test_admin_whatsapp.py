"""Admin WhatsApp routes and the intentionally simple bridge contract."""

import json

import httpx
import pytest
from app.core.admin_auth import ADMIN_SESSION_COOKIE
from app.main import app
from app.models.admin import Admin
from app.models.whatsapp_notification import DEFAULT_MESSAGE_TEMPLATE
from app.routes.admin_whatsapp import get_gateway
from app.services.admin_auth_service import create_admin_session
from app.services.whatsapp_gateway_service import WhatsAppGateway


@pytest.fixture
def admin(client, db_session):
    account = Admin(username="whatsapp-admin", password_hash="unused")
    db_session.add(account)
    db_session.commit()
    client.cookies.set(
        ADMIN_SESSION_COOKIE,
        create_admin_session(db_session, account, 1),
        path="/admin",
    )
    return account


@pytest.fixture
def bridge(client):
    state = {"state": "disconnected", "phone": None, "qr_available": False}
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer " + "x" * 40
        if request.url.path == "/api/status":
            return httpx.Response(200, json=state)
        if request.url.path == "/api/connect":
            state.update(state="qr", qr_available=True)
            return httpx.Response(202, json=state)
        if request.url.path == "/api/disconnect":
            state.update(state="disconnected", phone=None, qr_available=False)
            return httpx.Response(200, json=state)
        if request.url.path == "/api/qr":
            return httpx.Response(
                200, json=state | {"qr_data_url": "data:image/png;base64,Y29kZQ=="}
            )
        if request.url.path == "/api/messages":
            return httpx.Response(200, json={"sent": True})
        raise AssertionError(request.url.path)

    gateway = WhatsAppGateway(
        "http://bridge.test", "x" * 40, httpx.MockTransport(respond)
    )
    app.dependency_overrides[get_gateway] = lambda: gateway
    return state, requests


def test_dashboard_and_mutations_require_admin(client, bridge):
    for method, path in [
        ("get", "/admin/whatsapp"),
        ("get", "/admin/whatsapp/config"),
        ("get", "/admin/whatsapp/status"),
        ("get", "/admin/whatsapp/daily"),
        ("post", "/admin/whatsapp/connect"),
        ("post", "/admin/whatsapp/disconnect"),
        ("post", "/admin/whatsapp/settings"),
        ("post", "/admin/whatsapp/enabled"),
        ("post", "/admin/whatsapp/test"),
        ("post", "/admin/whatsapp/send-now"),
        ("post", "/admin/whatsapp/skip-today"),
        ("post", "/admin/whatsapp/cancel-skip"),
    ]:
        response = getattr(client, method)(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"
    assert bridge[1] == []


def test_connection_request_rejects_cross_origin_forms(client, admin, bridge):
    response = client.post(
        "/admin/whatsapp/connect", headers={"Origin": "https://another.example"}
    )
    assert response.status_code == 403
    assert bridge[1] == []


def test_connected_number_can_be_disconnected_after_confirmation(client, admin, bridge):
    state, requests = bridge
    state.update(state="connected", phone="6281234567890")
    assert "Putuskan koneksi" in client.get("/admin/whatsapp").text
    assert client.get("/admin/whatsapp/confirm/disconnect").status_code == 200
    response = client.post("/admin/whatsapp/disconnect", follow_redirects=False)
    assert response.status_code == 303
    assert state["state"] == "disconnected"
    assert any(request.url.path == "/api/disconnect" for request in requests)
    assert "Minta kode QR" in client.get("/admin/whatsapp").text


def test_connection_settings_and_real_test_message(
    client, admin, bridge, existing_student, db_session
):
    state, requests = bridge
    page = client.get("/admin/whatsapp")
    assert page.status_code == 200
    assert "Minta kode QR" in page.text
    assert "Safe Mode" in page.text
    assert 'class="button gateway-service-switch"' in page.text
    assert 'type="time"' in page.text
    assert 'value="09:00"' in page.text
    assert client.get("/admin/whatsapp/config").json()["safe_mode"] is True
    assert (
        client.get("/admin/whatsapp/config").json()["message_template"]
        == DEFAULT_MESSAGE_TEMPLATE
    )

    started = client.post("/admin/whatsapp/connect", follow_redirects=False)
    assert started.status_code == 303
    assert "data:image/png;base64,Y29kZQ==" in client.get("/admin/whatsapp").text
    state.update(state="connected", phone="6281234567890", qr_available=False)
    fragment = client.get("/admin/whatsapp/status", headers={"HX-Request": "true"})
    assert "+6281234567890" in fragment.text
    assert "hx-trigger" not in fragment.text

    saved = client.post(
        "/admin/whatsapp/settings",
        data={
            "send_time": "08:45",
            "minimum_attendance": "12",
            "message_template": "Halo {{nama}} kelas {{kelas}}",
            "safe_mode": "true",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    config = client.get("/admin/whatsapp/config").json()
    assert config["send_time"] == "08:45"
    assert config["minimum_attendance"] == 12

    sent = client.post(
        "/admin/whatsapp/test",
        data={"test_number": "08111111111"},
        follow_redirects=False,
    )
    assert sent.status_code == 303
    message = next(
        request for request in requests if request.url.path == "/api/messages"
    )
    assert json.loads(message.content) == {
        "phone": "628111111111",
        "message": "Halo Nicholas Angle kelas 11B",
    }
    assert client.get("/admin/whatsapp/config").json()["today"]["state"] == "ready"

    invalid = client.post("/admin/whatsapp/test", data={"test_number": "bad"})
    assert invalid.status_code == 422
    assert "kode negara" in invalid.text


def test_settings_validation_and_toggle_are_persistent(client, admin, bridge):
    invalid = client.post(
        "/admin/whatsapp/settings",
        data={
            "send_time": "09:00",
            "minimum_attendance": "20",
            "message_template": "{{unknown}}",
        },
    )
    assert invalid.status_code == 422
    assert "variabel" in invalid.text
    assert client.get("/admin/whatsapp/config").json()["enabled"] is False
    assert client.get("/admin/whatsapp/confirm/enable").status_code == 200
    assert (
        client.post(
            "/admin/whatsapp/enabled", data={"enabled": "true"}, follow_redirects=False
        ).status_code
        == 303
    )
    assert client.get("/admin/whatsapp/config").json()["enabled"] is True
    assert (
        client.post(
            "/admin/whatsapp/enabled", data={"enabled": "false"}, follow_redirects=False
        ).status_code
        == 303
    )
    assert client.get("/admin/whatsapp/config").json()["enabled"] is False


def test_skip_and_cancel_have_separate_daily_state(client, admin, bridge):
    assert client.get("/admin/whatsapp/confirm/skip-today").status_code == 200
    assert (
        client.post("/admin/whatsapp/skip-today", follow_redirects=False).status_code
        == 303
    )
    today = client.get("/admin/whatsapp/config").json()["today"]
    assert today["state"] == "skipped"
    assert today["can_send_now"] is False
    assert today["can_cancel_skip"] is True
    assert client.post("/admin/whatsapp/skip-today").status_code == 409
    assert (
        client.post("/admin/whatsapp/cancel-skip", follow_redirects=False).status_code
        == 303
    )
    assert client.get("/admin/whatsapp/config").json()["today"]["state"] == "ready"


def test_manual_send_is_confirmed_and_uses_one_daily_run(
    client, admin, bridge, existing_student, db_session
):
    state, requests = bridge
    state.update(state="connected", phone="6281234567890")
    existing_student.guardian_phone = "+628111111111"
    db_session.commit()
    assert client.get("/admin/whatsapp/confirm/send-now").status_code == 200
    first = client.post("/admin/whatsapp/send-now", follow_redirects=False)
    assert first.status_code == 303
    assert client.get("/admin/whatsapp/config").json()["today"]["state"] == "completed"
    assert client.post("/admin/whatsapp/send-now").status_code == 409
    assert client.post("/admin/whatsapp/skip-today").status_code == 409
    assert (
        len([request for request in requests if request.url.path == "/api/messages"])
        == 1
    )


def test_unavailable_bridge_and_bad_qr_are_safe(client, admin, bridge):
    app.dependency_overrides[get_gateway] = lambda: WhatsAppGateway(
        "http://bridge.test", ""
    )
    page = client.get("/admin/whatsapp")
    assert page.status_code == 200
    assert "belum dikonfigurasi" in page.text
    assert client.post("/admin/whatsapp/connect").status_code == 503

    state, _requests = bridge
    state.update(state="qr", qr_available=True)

    def bad_qr(request):
        if request.url.path == "/api/status":
            return httpx.Response(200, json=state)
        return httpx.Response(200, json=state | {"qr_data_url": "javascript:alert(1)"})

    app.dependency_overrides[get_gateway] = lambda: WhatsAppGateway(
        "http://bridge.test", "x" * 40, httpx.MockTransport(bad_qr)
    )
    assert "javascript:alert" not in client.get("/admin/whatsapp").text
