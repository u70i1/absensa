"""Browser-facing administrator authentication flows."""

from app.models.admin import Admin, AdminSession
from app.services.admin_auth_service import hash_password
from sqlalchemy import func, select


def create_admin(
    db_session, username="admin", password="correct-password", active=True
):
    admin = Admin(
        username=username,
        password_hash=hash_password(password),
        active=active,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


def test_admin_login_page_and_protected_routes(client):
    login = client.get("/admin")
    assert login.status_code == 200
    assert "Masuk sebagai admin" in login.text

    for path in ("/admin/students", "/admin/classes"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"

    htmx_response = client.get(
        "/admin/students", headers={"HX-Request": "true"}, follow_redirects=False
    )
    assert htmx_response.status_code == 401
    assert htmx_response.headers["HX-Redirect"] == "/admin"


def test_invalid_credentials_return_one_generic_error(client, db_session):
    create_admin(db_session)
    response = client.post(
        "/admin",
        data={"username": "admin", "password": "wrong-password"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Nama pengguna atau kata sandi tidak valid." in response.text
    assert "wrong-password" not in response.text


def test_login_session_redirects_and_logout_invalidates_it(client, db_session):
    create_admin(db_session)
    response = client.post(
        "/admin",
        data={"username": " ADMIN ", "password": "correct-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/students"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert db_session.scalar(select(func.count()).select_from(AdminSession)) == 1

    assert client.get("/admin/students").status_code == 200
    already_authenticated = client.get("/admin", follow_redirects=False)
    assert already_authenticated.status_code == 303
    assert already_authenticated.headers["location"] == "/admin/students"

    logout = client.post("/admin/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/"
    assert db_session.scalar(select(func.count()).select_from(AdminSession)) == 0
    assert client.get("/admin/students", follow_redirects=False).status_code == 303


def test_inactive_admin_cannot_login(client, db_session):
    create_admin(db_session, active=False)
    response = client.post(
        "/admin",
        data={"username": "admin", "password": "correct-password"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Nama pengguna atau kata sandi tidak valid." in response.text
