"""Password throttling, browser privacy and worker response validation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from app.models.login_throttle import LoginThrottle
from app.services import login_throttle_service as throttle
from app.services.whatsapp_gateway_service import GatewayProblem, WhatsAppGateway
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tests.conftest import validate_test_database


@pytest.mark.parametrize("path", ["/admin", "/trusteddevice/login"])
def test_password_login_throttles_unknown_accounts(client, path):
    for number in range(5):
        response = client.post(
            path,
            data={
                "username": " UNKNOWN " if number % 2 else "unknown",
                "password": "wrong",
            },
        )
        assert response.status_code == 401
    response = client.post(
        path,
        data={"username": "unknown", "password": "wrong"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert "wrong" not in response.text


def test_account_budget_spans_sources_and_expires(db_session, monkeypatch):
    start = datetime(2026, 9, 24, tzinfo=timezone.utc)
    monkeypatch.setattr(throttle, "now_utc", lambda: start)
    for number in range(5):
        throttle.reserve_attempt(db_session, "admin", "admin", f"source-{number}")
    with pytest.raises(throttle.LoginThrottled):
        throttle.reserve_attempt(db_session, "admin", " ADMIN ", "new-source")
    monkeypatch.setattr(throttle, "now_utc", lambda: start + throttle.WINDOW)
    throttle.reserve_attempt(db_session, "admin", "admin", "new-source")


def test_source_budget_limits_username_spraying_and_bucket_growth(db_session):
    for number in range(30):
        throttle.reserve_attempt(db_session, "admin", f"unknown-{number}", "one-source")
    before = len(list(db_session.scalars(select(LoginThrottle))))
    for number in range(10):
        with pytest.raises(throttle.LoginThrottled):
            throttle.reserve_attempt(
                db_session, "admin", f"more-{number}", "one-source"
            )
    assert len(list(db_session.scalars(select(LoginThrottle)))) == before


def test_concurrent_login_attempts_share_persisted_budget(engine):
    realm = uuid4().hex
    barrier = Barrier(8)

    def attempt(_):
        barrier.wait(timeout=10)
        with Session(engine) as db:
            try:
                throttle.reserve_attempt(db, realm, "unknown", "source")
                return 200
            except throttle.LoginThrottled:
                return 429

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        assert results.count(200) == 5 and results.count(429) == 3
        with Session(engine) as db, pytest.raises(throttle.LoginThrottled):
            throttle.reserve_attempt(db, realm, "unknown", "another-source")
    finally:
        from hashlib import sha256

        keys = [
            sha256(f"{realm}:{value}".encode()).hexdigest()
            for value in ("account:unknown", "source:source", "source:another-source")
        ]
        with Session(engine) as db:
            db.execute(delete(LoginThrottle).where(LoginThrottle.key.in_(keys)))
            db.commit()


def test_browser_privacy_headers_and_escaping(
    client, authenticated_data_api, existing_student, db_session
):
    existing_student.name = '<img src=x onerror="alert(1)">'
    db_session.commit()
    response = client.get("/admin/students")
    assert response.status_code == 200
    assert existing_student.name not in response.text
    assert "&lt;img" in response.text
    assert 'hx-history="false"' in response.text
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("state", [[], {}, None, 1])
def test_malformed_worker_state_is_unavailable(state):
    bridge = WhatsAppGateway(
        "http://bridge",
        "a" * 32,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"state": state})
        ),
    )
    assert bridge.status().state == "unavailable"


@pytest.mark.parametrize(
    "status,payload", [(200, {}), (200, {"sent": False}), (302, {"sent": True})]
)
def test_worker_send_requires_success_acknowledgement(status, payload):
    bridge = WhatsAppGateway(
        "http://bridge",
        "a" * 32,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=payload)
        ),
    )
    with pytest.raises(GatewayProblem):
        bridge.send_message("6281234567890", "Mocked message")


def test_destructive_suite_requires_explicit_separate_database(monkeypatch):
    application = "postgresql://app:password@db/school"
    test = "postgresql://test:password@db/test_school"
    monkeypatch.delenv("ABSENSA_ALLOW_TEST_DATABASE_RESET", raising=False)
    with pytest.raises(RuntimeError):
        validate_test_database(test, application)
    monkeypatch.setenv("ABSENSA_ALLOW_TEST_DATABASE_RESET", "1")
    with pytest.raises(RuntimeError):
        validate_test_database(
            "postgresql+psycopg2://other:password@db:5432/school", application
        )
    validate_test_database(test, application)


def test_database_error_hides_bound_student_information(engine):
    from app.db.session import engine as application_engine
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DBAPIError

    secret = "Student name and guardian contact"
    protected = create_engine(
        engine.url, hide_parameters=application_engine.hide_parameters
    )
    try:
        with protected.connect() as connection, pytest.raises(DBAPIError) as failure:
            connection.execute(
                text("SELECT 1/0 + length(:contact)"), {"contact": secret}
            )
        assert secret not in str(failure.value)
        assert "SQL parameters hidden" in str(failure.value)
    finally:
        protected.dispose()
