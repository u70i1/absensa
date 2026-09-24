"""Admin dashboard and bridge contract without a live WhatsApp account."""

import httpx
import pytest
from app.core.admin_auth import ADMIN_SESSION_COOKIE
from app.main import app
from app.models.admin import Admin
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
        if request.url.path == "/api/qr":
            return httpx.Response(
                200, json=state | {"qr_data_url": "data:image/png;base64,Y29kZQ=="}
            )
        if request.url.path == "/api/messages/test":
            return httpx.Response(200, json={"sent": True})
        raise AssertionError(request.url.path)

    gateway = WhatsAppGateway(
        "http://bridge.test", "x" * 40, httpx.MockTransport(respond)
    )
    app.dependency_overrides[get_gateway] = lambda: gateway
    return state, requests


def test_dashboard_and_bridge_actions_require_admin(client, bridge):
    for method, path in [
        ("get", "/admin/whatsapp"),
        ("get", "/admin/whatsapp/status"),
        ("post", "/admin/whatsapp/connect"),
        ("post", "/admin/whatsapp/send"),
    ]:
        response = getattr(client, method)(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"
    assert bridge[1] == []


def test_connection_request_rejects_cross_origin_forms(client, admin, bridge):
    response = client.post(
        "/admin/whatsapp/connect",
        headers={"Origin": "https://another.example"},
    )
    assert response.status_code == 403
    assert bridge[1] == []


def test_qr_to_connected_and_test_message_flow(client, admin, bridge):
    state, requests = bridge
    page = client.get("/admin/whatsapp")
    assert page.status_code == 200
    assert "Minta kode QR" in page.text
    assert 'aria-current="page"' in page.text

    started = client.post("/admin/whatsapp/connect", follow_redirects=False)
    assert started.status_code == 303
    assert started.headers["location"] == "/admin/whatsapp"
    qr_page = client.get("/admin/whatsapp")
    assert "data:image/png;base64,Y29kZQ==" in qr_page.text
    assert 'hx-trigger="every 5s"' in qr_page.text

    state.update(state="connected", phone="6281234567890", qr_available=False)
    fragment = client.get("/admin/whatsapp/status", headers={"HX-Request": "true"})
    assert fragment.status_code == 200
    assert "+6281234567890" in fragment.text
    assert "Kirim pesan uji" in fragment.text
    assert "hx-trigger" not in fragment.text

    invalid = client.post("/admin/whatsapp/send", data={"phone": "abc"})
    assert invalid.status_code == 422
    assert "kode negara" in invalid.text
    assert not any(request.url.path == "/api/messages/test" for request in requests)

    sent = client.post(
        "/admin/whatsapp/send",
        data={"phone": "+62 811-1111-111"},
        follow_redirects=False,
    )
    assert sent.status_code == 303
    assert sent.headers["location"] == "/admin/whatsapp?sent=1"
    message_request = next(
        request for request in requests if request.url.path == "/api/messages/test"
    )
    assert message_request.content == b'{"phone":"628111111111"}'
    assert "Pesan uji berhasil dikirim" in client.get(sent.headers["location"]).text


def test_unavailable_bridge_and_bad_qr_are_safe(client, admin, bridge):
    app.dependency_overrides[get_gateway] = lambda: WhatsAppGateway(
        "http://bridge.test", ""
    )
    page = client.get("/admin/whatsapp")
    assert page.status_code == 200
    assert "belum dikonfigurasi" in page.text
    assert "bridge.test" not in page.text
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
