"""
Shared pytest fixtures for the whole test suite.

Fixture chain (each depends on the one above it, same pattern as your
base_number -> doubled exercise):

    engine        (session-scoped, runs Alembic migrations once)
      -> connection  (function-scoped, opens a transaction)
           -> db_session  (function-scoped, nested SAVEPOINT inside that transaction)
                -> client  (function-scoped, FastAPI TestClient using db_session)
"""

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
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


@pytest.fixture
def class_factory(db_session):
    """Seed a single class entry"""

    def _make_class(class_name="Flock A"):
        class_ = Class(class_name=class_name)
        db_session.add(class_)
        db_session.commit()
        db_session.refresh(class_)
        return class_

    return _make_class


@pytest.fixture
def student_factory(db_session):
    """Seed a single student entry"""

    def _make_student(name="Shaun", class_id=None, nisn="1000000001", current=True):
        student = Student(name=name, class_id=class_id, nisn=nisn, current=current)
        db_session.add(student)
        db_session.commit()
        db_session.refresh(student)
        return student

    return _make_student


@pytest.fixture
def scan_log_factory(
    db_session,
    timezone: ZoneInfo | None = None,
) -> Callable:
    """Seed a single scan log entry"""

    if timezone is None:
        timezone = ZoneInfo(settings.timezone)

    def _make_scan_log(student: Student, when: datetime | None = None) -> ScanLog:
        if when is None:
            when = datetime.now(tz=timezone)

        class_name = student.class_.class_name if student.class_ is not None else None
        scan_log = ScanLog(
            student_id=student.id,
            name=student.name,
            class_name=class_name,
            timestamp=when,
        )
        db_session.add(scan_log)
        db_session.commit()
        db_session.refresh(scan_log)
        return scan_log

    return _make_scan_log


SEED_STUDENTS = [
    {"name": "Shaun", "class_index": 0, "nisn": "1000000001"},
    {"name": "Ed", "class_index": 0, "nisn": "1000000002"},
    {"name": "Liz", "class_index": 0, "nisn": "1000000003"},
    {"name": "David", "class_index": 0, "nisn": "1000000004"},
    {"name": "Dianne", "class_index": 0, "nisn": "1000000005"},
    {"name": "Barbara", "class_index": 0, "nisn": "1000000006"},
    {"name": "Philip", "class_index": 0, "nisn": "1000000007"},
    {"name": "Pete", "class_index": 0, "nisn": "1000000008"},
    {"name": "Yvonne", "class_index": 1, "nisn": "1000000009"},
    {"name": "Tom", "class_index": 1, "nisn": "1000000010"},
    {"name": "Declan", "class_index": 2, "nisn": "1000000011"},
    {"name": "Alan", "class_index": 3, "nisn": "1000000100"},
]

SEED_CLASSES = ["10A", "10B", "10C", "10D"]


@pytest.fixture
def seeded_students_and_classes(db_session):
    """Insert SEED_STUDENTS and SEED_CLASSES and return them."""
    classes = [Class(class_name=class_) for class_ in SEED_CLASSES]
    db_session.add_all(classes)

    db_session.flush()

    students = [
        Student(
            name=data["name"],
            nisn=data["nisn"],
            class_id=classes[data["class_index"]].class_id,
        )
        for data in SEED_STUDENTS
    ]
    db_session.add_all(students)
    db_session.commit()
    return students


@pytest.fixture
def existing_class(class_factory):
    """A default class (11B) for most tests."""
    return class_factory(class_name="11B")


@pytest.fixture
def existing_student(student_factory, existing_class):
    """A single active, scannable student the default case most tests need."""
    return student_factory(
        name="Nicholas Angle",
        nisn="1234567890",
        class_id=existing_class.class_id,
        current=True,
    )
