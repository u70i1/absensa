"""
Shared pytest fixtures for the whole test suite.

Fixture chain (each depends on the one above it, same pattern as your
base_number -> doubled exercise):

    engine        (session-scoped, runs Alembic migrations once)
      -> connection  (function-scoped, opens a transaction)
           -> db_session  (function-scoped, nested SAVEPOINT inside that transaction)
                -> client  (function-scoped, FastAPI TestClient using db_session)
"""

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def run_migrations(url: str, direction: str = "upgrade") -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    if direction == "upgrade":
        command.upgrade(alembic_cfg, "head")
    else:
        command.downgrade(alembic_cfg, "base")


@pytest.fixture(scope="session")
def engine():
    """One engine for the whole test run, schema built via real Alembic migrations."""
    run_migrations(settings.test_database_url, "upgrade")

    engine = create_engine(settings.test_database_url)
    yield engine
    engine.dispose()

    run_migrations(settings.test_database_url, "downgrade")


@pytest.fixture
def connection(engine):
    """A single connection + outer transaction, rolled back after every test."""
    connection = engine.connect()
    transaction = connection.begin()

    yield connection

    transaction.rollback()
    connection.close()


@pytest.fixture
def db_session(connection):
    """
    A Session bound to `connection`, nested in a SAVEPOINT.

    Even if the endpoint under test calls db.commit(), the listener below
    immediately reopens a SAVEPOINT so the outer `connection` fixture can
    still roll everything back at teardown.
    """
    session = sessionmaker(bind=connection)()
    connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if not connection.in_nested_transaction():
            connection.begin_nested()

    yield session

    session.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with get_db overridden to use the isolated test session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    yield TestClient(app)

    app.dependency_overrides.clear()
