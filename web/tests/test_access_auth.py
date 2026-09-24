"""Two-layer authentication, persistent binding, PIN lockout and administration."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from secrets import token_urlsafe
from threading import Barrier

import pytest
from app.core.access_auth import DEVICE_COOKIE, OPERATOR_COOKIE
from app.core.admin_auth import ADMIN_SESSION_COOKIE
from app.core.config import settings
from app.models.access import Operator, OperatorSession, TrustedDevice
from app.models.admin import Admin
from app.services import access_auth_service as auth
from app.services import access_management_service as management
from app.services.admin_auth_service import (
    create_admin_session,
    hash_password,
    password_hasher,
)
from app.services.exceptions import AppException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

PASSWORD = "device-password-strong"
PIN = "001234"
PASSWORD_HASH = hash_password(PASSWORD)
PIN_HASH = hash_password(PIN)


@pytest.fixture
def accounts(db_session):
    device = TrustedDevice(username="gate-one", password_hash=PASSWORD_HASH)
    operators = [
        Operator(display_name="Teacher", pin_hash=PIN_HASH),
        Operator(display_name="Teacher", pin_hash=PIN_HASH),
    ]
    db_session.add_all([device, *operators])
    db_session.commit()
    return device, operators


@pytest.fixture
def admin_session(client, db_session):
    admin = Admin(username="access-admin", password_hash=PASSWORD_HASH)
    db_session.add(admin)
    db_session.commit()
    client.cookies.set(
        ADMIN_SESSION_COOKIE, create_admin_session(db_session, admin, 1), path="/"
    )
    return admin


def device_login(client, **changes):
    return client.post(
        "/trusteddevice/login",
        data={"username": "gate-one", "password": PASSWORD, **changes},
        follow_redirects=False,
    )


def operator_login(client, operator, pin=PIN, **changes):
    return client.post(
        "/operator/login",
        data={"operator_id": str(operator.id), "pin": pin, **changes},
        follow_redirects=False,
    )


def test_binding_argon_persistence_and_single_browser(client, accounts, db_session):
    device, operators = accounts
    response = device_login(client, username=" GATE-ONE ")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/operator/login")
    token = client.cookies[DEVICE_COOKIE]
    cookie = next(
        c
        for c in response.headers.get_list("set-cookie")
        if c.startswith(DEVICE_COOKIE + "=")
    )
    assert (
        "Max-Age=34560000" in cookie
        and "HttpOnly" in cookie
        and "SameSite=lax" in cookie
        and "Path=/" in cookie
    )
    assert password_hasher.verify(device.password_hash, PASSWORD)
    db_session.refresh(device)
    assert (
        device.binding_hash == auth.token_digest(token) and device.binding_hash != token
    )
    assert device.bound_at is not None
    # Removing only a session cookie simulates a browser restart: persistent device remains.
    assert client.get("/operator/login").status_code == 200
    client.cookies.clear()
    assert (
        device_login(client).status_code == 409
    )  # Losing the cookie never frees a binding.
    assert "sudah terhubung" in device_login(client).text
    assert device_login(client, password="wrong").status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "wrong"},
        {"username": "unknown"},
        {"password": ""},
        {"password": "x" * 1025},
    ],
)
def test_device_login_failures_do_not_echo_secrets(client, accounts, changes):
    response = device_login(client, **changes)
    assert response.status_code == 401
    assert 'value="wrong"' not in response.text and PASSWORD not in response.text
    assert DEVICE_COOKIE not in client.cookies


def test_inactive_device_cannot_bind(client, accounts, db_session):
    accounts[0].active = False
    db_session.commit()
    assert device_login(client).status_code == 401


def test_operator_requires_device_and_pin_is_session_only(client, accounts, db_session):
    device, operators = accounts
    assert (
        operator_login(client, operators[0])
        .headers["location"]
        .startswith("/trusteddevice/login")
    )
    device_login(client)
    response = operator_login(client, operators[0])
    assert response.status_code == 303 and response.headers["location"] == "/operator"
    assert password_hasher.verify(operators[0].pin_hash, PIN)
    cookie = next(
        c
        for c in response.headers.get_list("set-cookie")
        if c.startswith(OPERATOR_COOKIE + "=")
    )
    assert (
        "Max-Age" not in cookie
        and "expires=" not in cookie.lower()
        and "HttpOnly" in cookie
    )
    session = db_session.scalar(select(OperatorSession))
    assert session.token_hash == auth.token_digest(client.cookies[OPERATOR_COOKIE])
    assert session.binding_hash == device.binding_hash
    assert client.get("/operator").status_code == 200
    client.cookies.delete(OPERATOR_COOKIE)
    assert (
        client.get("/operator", follow_redirects=False)
        .headers["location"]
        .startswith("/operator/login")
    )
    assert client.get("/operator/login").status_code == 200


@pytest.mark.parametrize(
    "pin", ["", "12345", "1234567", "abcdef", "１２３４５６", " 001234", "000000"]
)
def test_pin_validation_and_failure_count(client, accounts, db_session, pin):
    device_login(client)
    response = operator_login(client, accounts[1][0], pin=pin)
    assert response.status_code == 401
    assert (
        'value="' + pin + '"' not in response.text
        if pin
        else 'name="pin"' in response.text
    )
    db_session.refresh(accounts[0])
    assert accounts[0].pin_failures == 1
    assert db_session.scalar(select(OperatorSession)) is None


def test_lockout_device_wide_expiry_and_reset(
    client, accounts, db_session, monkeypatch
):
    device, operators = accounts
    device_login(client)
    start = auth.now_utc()
    monkeypatch.setattr(auth, "now_utc", lambda: start)
    for i in range(5):
        response = operator_login(client, operators[i % 2], pin="999999")
        assert response.status_code == (429 if i == 4 else 401)
    db_session.refresh(device)
    assert device.pin_failures == 5 and device.locked_until == start + timedelta(
        minutes=5
    )
    assert operator_login(client, operators[1]).status_code == 429
    assert "Retry-After" in response.headers and "UTC" in response.text
    monkeypatch.setattr(
        auth, "now_utc", lambda: start + timedelta(minutes=4, seconds=59)
    )
    assert operator_login(client, operators[0]).status_code == 429
    monkeypatch.setattr(auth, "now_utc", lambda: start + timedelta(minutes=5))
    assert operator_login(client, operators[1]).status_code == 303
    db_session.refresh(device)
    assert device.pin_failures == 0 and device.locked_until is None


def test_success_resets_consecutive_failure_counter(client, accounts, db_session):
    device_login(client)
    for _ in range(4):
        operator_login(client, accounts[1][0], pin="999999")
    assert operator_login(client, accounts[1][0]).status_code == 303
    db_session.refresh(accounts[0])
    assert accounts[0].pin_failures == 0
    client.post("/operator/logout")
    assert operator_login(client, accounts[1][0], pin="999999").status_code == 401
    db_session.refresh(accounts[0])
    assert accounts[0].pin_failures == 1


def test_operator_switch_and_device_logout(client, accounts, db_session):
    device_login(client)
    token = client.cookies[DEVICE_COOKIE]
    operator_login(client, accounts[1][0])
    old_operator_token = client.cookies[OPERATOR_COOKIE]
    response = client.post("/operator/logout", follow_redirects=False)
    assert response.headers["location"] == "/operator/login"
    assert (
        client.cookies[DEVICE_COOKIE] == token and OPERATOR_COOKIE not in client.cookies
    )
    assert db_session.scalar(select(OperatorSession)) is None
    assert operator_login(client, accounts[1][1]).status_code == 303
    assert client.cookies[OPERATOR_COOKIE] != old_operator_token
    response = client.post("/trusteddevice/logout", follow_redirects=False)
    assert response.headers["location"] == "/trusteddevice/login"
    assert DEVICE_COOKIE not in client.cookies and OPERATOR_COOKIE not in client.cookies
    db_session.refresh(accounts[0])
    assert accounts[0].binding_hash is None
    assert db_session.scalar(select(OperatorSession)) is None
    assert device_login(client).status_code == 303
    assert client.cookies[DEVICE_COOKIE] != token


def test_revocation_rebinding_and_operator_invariant(
    client, accounts, db_session, admin_session
):
    device_login(client)
    old_device = client.cookies[DEVICE_COOKIE]
    operator_login(client, accounts[1][0])
    old_operator = client.cookies[OPERATOR_COOKIE]
    response = client.post(
        f"/admin/access/devices/{accounts[0].id}/revoke", follow_redirects=False
    )
    assert response.status_code == 303
    assert db_session.scalar(select(OperatorSession)) is None
    assert (
        client.get("/operator", follow_redirects=False)
        .headers["location"]
        .startswith("/trusteddevice/login")
    )
    assert DEVICE_COOKIE not in client.cookies and OPERATOR_COOKIE not in client.cookies
    assert device_login(client).status_code == 303
    assert client.cookies[DEVICE_COOKIE] != old_device
    client.cookies.set(OPERATOR_COOKIE, old_operator, path="/")
    assert (
        client.get("/operator", follow_redirects=False)
        .headers["location"]
        .startswith("/operator/login")
    )


@pytest.mark.parametrize("state", ["none", "device", "both"])
@pytest.mark.parametrize(
    "path", ["/trusteddevice/login", "/operator/login", "/operator"]
)
def test_smart_routing(client, accounts, state, path):
    if state != "none":
        device_login(client)
    if state == "both":
        operator_login(client, accounts[1][0])
    response = client.get(path, follow_redirects=False)
    expected = {
        ("none", "/trusteddevice/login"): None,
        ("none", "/operator/login"): "/trusteddevice/login",
        ("none", "/operator"): "/trusteddevice/login",
        ("device", "/trusteddevice/login"): "/operator/login",
        ("device", "/operator/login"): None,
        ("device", "/operator"): "/operator/login",
        ("both", "/trusteddevice/login"): "/operator",
        ("both", "/operator/login"): "/operator",
        ("both", "/operator"): None,
    }[(state, path)]
    assert response.status_code == (303 if expected else 200)
    if expected:
        assert response.headers["location"].split("?")[0] == expected
    assert client.get(path).status_code == 200  # Finite redirect chain.


@pytest.mark.parametrize(
    "destination",
    [
        "https://evil.test",
        "//evil.test",
        "/\\evil.test",
        "/operator/login",
        "/trusteddevice/login",
        "/operator/logout",
        "/admin",
        "/operator%2flogin",
    ],
)
def test_safe_return_destinations_do_not_loop(client, accounts, destination):
    assert device_login(client, next=destination).status_code == 303
    response = operator_login(client, accounts[1][0], next=destination)
    assert response.headers["location"] == "/operator"
    assert (
        client.get("/trusteddevice/login", params={"next": destination}).status_code
        == 200
    )


def test_logout_without_auth_and_empty_operators(client, accounts, db_session):
    assert client.post("/operator/logout").status_code == 200
    assert client.post("/trusteddevice/logout").status_code == 200
    for operator in accounts[1]:
        operator.active = False
    db_session.commit()
    device_login(client)
    page = client.get("/operator/login")
    assert "Belum ada operator aktif" in page.text
    assert operator_login(client, accounts[1][0]).status_code == 401


def test_operator_session_is_not_portable_to_another_device(
    client, accounts, db_session
):
    device_login(client)
    operator_login(client, accounts[1][0])
    token = client.cookies[OPERATOR_COOKIE]
    another = TrustedDevice(username="another", password_hash=PASSWORD_HASH)
    db_session.add(another)
    db_session.commit()
    client.cookies.clear()
    device_login(client, username="another")
    client.cookies.set(OPERATOR_COOKIE, token, path="/")
    assert (
        client.get("/operator", follow_redirects=False)
        .headers["location"]
        .startswith("/operator/login")
    )
    client.cookies.clear()
    client.cookies.set(OPERATOR_COOKIE, token, path="/")
    assert (
        client.get("/operator", follow_redirects=False)
        .headers["location"]
        .startswith("/trusteddevice/login")
    )


def test_admin_management_validation_and_no_secret_echo(
    client, admin_session, db_session
):
    for kind, name, secret in [
        ("devices", "Front Desk", PASSWORD),
        ("operators", "Teacher", PIN),
    ]:
        response = client.post(
            f"/admin/access/{kind}",
            data={"name": name, "secret": secret, "active": "true"},
            follow_redirects=False,
        )
        assert response.status_code == 303
    device = db_session.scalar(select(TrustedDevice))
    operator = db_session.scalar(select(Operator))
    assert device.username == "front desk" and device.created_by == admin_session.id
    assert password_hasher.verify(
        device.password_hash, PASSWORD
    ) and password_hasher.verify(operator.pin_hash, PIN)
    for path in [
        "/admin/access",
        f"/admin/access/devices/{device.id}/edit",
        f"/admin/access/operators/{operator.id}/edit",
    ]:
        page = client.get(path)
        assert page.status_code == 200
        for secret in [PASSWORD, PIN, device.password_hash, operator.pin_hash]:
            assert secret not in page.text
    invalid = client.post(
        "/admin/access/operators",
        data={"name": "Bad", "secret": "bad-pin", "active": "true"},
        headers={"HX-Request": "true"},
    )
    assert invalid.status_code == 422 and "bad-pin" not in invalid.text
    assert invalid.headers["X-Admin-Fragment"] == "modal"
    assert (
        client.post(
            "/admin/access/devices",
            data={"name": " FRONT DESK ", "secret": PASSWORD, "active": "true"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "kind,action",
    [
        ("devices", "disable"),
        ("devices", "password"),
        ("devices", "delete"),
        ("operators", "disable"),
        ("operators", "pin"),
        ("operators", "delete"),
    ],
)
def test_admin_changes_end_active_sessions(
    client, accounts, db_session, admin_session, kind, action
):
    device_login(client)
    operator_login(client, accounts[1][0])
    item = accounts[0] if kind == "devices" else accounts[1][0]
    if action == "delete":
        response = client.post(
            f"/admin/access/{kind}/{item.id}/delete", follow_redirects=False
        )
    else:
        response = client.post(
            f"/admin/access/{kind}/{item.id}/edit",
            data={
                "name": "Updated",
                "active": "false" if action == "disable" else "true",
                "secret": "new-password"
                if action == "password"
                else "987654"
                if action == "pin"
                else "",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert db_session.scalar(select(OperatorSession)) is None
    redirect = client.get("/operator", follow_redirects=False)
    assert redirect.headers["location"].startswith(
        "/trusteddevice/login" if kind == "devices" else "/operator/login"
    )


def test_rename_preserves_secrets_and_allows_all_devices(
    client, accounts, db_session, admin_session
):
    device_login(client)
    operator_login(client, accounts[1][0])
    operator = accounts[1][0]
    response = client.post(
        f"/admin/access/operators/{operator.id}/edit",
        data={"name": "New teacher", "secret": "", "active": "true"},
    )
    assert response.status_code == 200
    db_session.refresh(operator)
    assert operator.pin_hash == PIN_HASH
    assert client.get("/operator").status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.test"},
        {"Origin": "null"},
        {"Origin": "http://testserver.evil"},
        {"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_csrf_rejects_cross_origin_before_mutation(client, accounts, headers):
    response = client.post(
        "/trusteddevice/login",
        data={"username": "gate-one", "password": PASSWORD},
        headers=headers,
    )
    assert response.status_code == 403 and DEVICE_COOKIE not in client.cookies


def test_csrf_missing_origin_and_same_origin_referer(client, accounts):
    client.headers.pop("Origin")
    assert device_login(client).status_code == 403
    client.headers["Referer"] = "http://testserver/trusteddevice/login"
    assert device_login(client).status_code == 303


def test_admin_auth_and_csrf_protect_account_mutations(
    client, accounts, admin_session, db_session
):
    device_login(client)
    response = client.post(
        f"/admin/access/devices/{accounts[0].id}/revoke",
        headers={"Origin": "https://evil.test"},
    )
    assert response.status_code == 403
    db_session.refresh(accounts[0])
    assert accounts[0].binding_hash
    client.cookies.delete(ADMIN_SESSION_COOKIE)
    assert (
        client.get("/admin/access", follow_redirects=False).headers["location"]
        == "/admin"
    )
    assert (
        client.post(
            "/admin/access/operators",
            data={"name": "Evil", "secret": "123456"},
            follow_redirects=False,
        ).headers["location"]
        == "/admin"
    )


def test_cookie_secure_configuration(client, accounts, monkeypatch):
    monkeypatch.setattr(settings, "access_cookie_secure", True)
    response = device_login(client)
    assert any(
        "Secure" in c and c.startswith(DEVICE_COOKIE + "=")
        for c in response.headers.get_list("set-cookie")
    )


def test_existing_api_cannot_bypass_operator_or_admin_auth(
    client, accounts, existing_student
):
    assert (
        client.post(
            "/scans", json={"nisn": existing_student.nisn}, follow_redirects=False
        )
        .headers["location"]
        .startswith("/trusteddevice/login")
    )
    assert (
        client.get("/students", follow_redirects=False).headers["location"] == "/admin"
    )
    assert (
        client.post("/students", json={}, follow_redirects=False).headers["location"]
        == "/admin"
    )
    device_login(client)
    assert (
        client.get("/scans", follow_redirects=False)
        .headers["location"]
        .startswith("/operator/login")
    )
    operator_login(client, accounts[1][0])
    assert (
        client.post("/scans", json={"nisn": existing_student.nisn}).status_code == 200
    )
    assert client.get("/scans").status_code == 200
    assert (
        client.delete("/scans/1", follow_redirects=False).headers["location"]
        == "/admin"
    )


def test_operator_application_scan_and_htmx_revocation(
    client, accounts, existing_student, db_session
):
    device_login(client)
    operator_login(client, accounts[1][0])
    response = client.post(
        "/operator/scans",
        data={"nisn": existing_student.nisn},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200 and existing_student.name in response.text
    assert response.headers["X-Operator-Fragment"] == "scan"
    assert (
        client.post("/operator/scans", data={"nisn": existing_student.nisn}).status_code
        == 409
    )
    assert client.post("/operator/scans", data={"nisn": "123"}).status_code == 422
    management.manage_account(db_session, "devices", accounts[0].id, "revoke")
    response = client.get(
        "/operator", headers={"HX-Request": "true"}, follow_redirects=False
    )
    assert response.status_code == 401 and response.headers["HX-Redirect"].startswith(
        "/trusteddevice/login"
    )


def test_concurrent_binding_and_pin_failures_are_serialized(engine):
    """Independent committed connections exercise real PostgreSQL row locks."""
    username = ("concurrent-" + token_urlsafe(8)).lower()
    with Session(engine) as db:
        device = TrustedDevice(username=username, password_hash=PASSWORD_HASH)
        operator = Operator(display_name="Concurrent", pin_hash=PIN_HASH)
        db.add_all([device, operator])
        db.commit()
        device_id, operator_id = device.id, operator.id
    binding_barrier = Barrier(2)

    def bind(_):
        binding_barrier.wait(timeout=10)
        with Session(engine) as db:
            try:
                return auth.bind_device(db, username, PASSWORD)
            except AppException as exc:
                return exc.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(bind, range(2)))
        assert results.count(409) == 1
        token = next(result for result in results if isinstance(result, str))
        attempt_barrier = Barrier(8)

        def fail(_):
            attempt_barrier.wait(timeout=10)
            with Session(engine) as db:
                try:
                    auth.login_operator(db, token, str(operator_id), "999999")
                except AppException as exc:
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            attempts = list(pool.map(fail, range(8)))
        assert attempts.count(401) == 4 and attempts.count(429) == 4
        with Session(engine) as db:
            device = db.get(TrustedDevice, device_id)
            assert device.pin_failures == 5 and device.locked_until > auth.now_utc()
            assert (
                db.scalar(
                    select(OperatorSession).where(
                        OperatorSession.device_id == device_id
                    )
                )
                is None
            )
    finally:
        with Session(engine) as db:
            db.execute(delete(TrustedDevice).where(TrustedDevice.id == device_id))
            db.execute(delete(Operator).where(Operator.id == operator_id))
            db.commit()


def test_manual_device_rebind_cannot_reset_pin_lockout(client, accounts, db_session):
    device_login(client)
    for _ in range(5):
        operator_login(client, accounts[1][0], pin="999999")
    locked_until = accounts[0].locked_until
    assert (
        client.post("/trusteddevice/logout", follow_redirects=False).status_code == 303
    )
    assert device_login(client).status_code == 303
    assert operator_login(client, accounts[1][1]).status_code == 429
    db_session.refresh(accounts[0])
    assert accounts[0].locked_until == locked_until and accounts[0].pin_failures == 5


def test_expired_lock_starts_new_failure_window(
    client, accounts, db_session, monkeypatch
):
    device_login(client)
    start = auth.now_utc()
    monkeypatch.setattr(auth, "now_utc", lambda: start)
    for _ in range(5):
        operator_login(client, accounts[1][0], pin="999999")
    monkeypatch.setattr(auth, "now_utc", lambda: start + timedelta(minutes=5))
    assert operator_login(client, accounts[1][1], pin="999999").status_code == 401
    db_session.refresh(accounts[0])
    assert accounts[0].locked_until is None and accounts[0].pin_failures == 1


def test_missing_and_unknown_operator_ids_count_against_device(
    client, accounts, db_session
):
    device_login(client)
    for operator_id in ["", "not-an-id", "999999999999999999999999", "2147483647"]:
        response = client.post(
            "/operator/login", data={"operator_id": operator_id, "pin": PIN}
        )
        assert response.status_code == 401
    db_session.refresh(accounts[0])
    assert accounts[0].pin_failures == 4


def test_all_operators_can_log_in_on_multiple_devices(client, accounts, db_session):
    device_login(client)
    operator_login(client, accounts[1][0])
    another = TrustedDevice(username="other-gate", password_hash=PASSWORD_HASH)
    db_session.add(another)
    db_session.commit()
    client.cookies.clear()
    assert device_login(client, username="other-gate").status_code == 303
    assert operator_login(client, accounts[1][0]).status_code == 303
    assert len(list(db_session.scalars(select(OperatorSession)))) == 2


def test_safe_local_destination_and_tampered_tokens(client, accounts):
    client.cookies.set(DEVICE_COOKIE, "not-real", path="/")
    client.cookies.set(OPERATOR_COOKIE, "not-real", path="/")
    assert (
        client.get("/operator", follow_redirects=False)
        .headers["location"]
        .startswith("/trusteddevice/login")
    )
    assert device_login(client, next="/operator?view=today").status_code == 303
    assert (
        operator_login(client, accounts[1][0], next="/operator?view=today").headers[
            "location"
        ]
        == "/operator?view=today"
    )
    assert (
        client.get("/trusteddevice/login", params={"next": "http://["}).status_code
        == 200
    )


def test_https_operator_cookie_is_secure_and_nonpersistent(
    client, accounts, monkeypatch
):
    monkeypatch.setattr(settings, "access_cookie_secure", True)
    client.base_url = "https://testserver"
    client.headers["Origin"] = "https://testserver"
    assert device_login(client).status_code == 303
    response = operator_login(client, accounts[1][0])
    assert response.status_code == 303
    cookie = next(
        c
        for c in response.headers.get_list("set-cookie")
        if c.startswith(OPERATOR_COOKIE + "=")
    )
    assert (
        "Secure" in cookie
        and "HttpOnly" in cookie
        and "Max-Age" not in cookie
        and "expires=" not in cookie.lower()
    )


def test_device_username_length_checked_after_normalization(client, admin_session):
    response = client.post(
        "/admin/access/devices",
        data={"name": "ß" * 100, "secret": PASSWORD, "active": "true"},
    )
    assert response.status_code == 422
    assert PASSWORD not in response.text
