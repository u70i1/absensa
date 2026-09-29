from unittest.mock import Mock

from app.db.session import get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


def test_health_checks_database_without_requiring_login():
    db = Mock()
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        db.execute.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_hides_database_connection_details():
    db = Mock()
    db.execute.side_effect = OperationalError("secret connection info", {}, Exception())
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/health")
        assert response.status_code == 503
        assert response.json() == {"ok": False}
        assert "secret" not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)
