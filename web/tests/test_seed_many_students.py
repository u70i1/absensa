"""Development seed never invents real-looking guardian contacts by default."""

import pytest
from app.models.student import Student
from scripts.seed_many_students import parse_args, seed_student_data
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker


def test_seed_number_options_are_explicit_and_validated():
    args = parse_args(["--count", "5"])
    assert args.test_number is None
    assert args.test_number_amount == 0
    args = parse_args(
        ["--count", "5", "--test-number", "081234567890", "--test-number-amount", "3"]
    )
    assert args.test_number == "081234567890"
    assert args.test_number_amount == 3
    for invalid in [
        ["--count", "5", "--test-number", "081234567890"],
        ["--count", "5", "--test-number-amount", "1"],
        ["--count", "5", "--test-number", "081234567890", "--test-number-amount", "6"],
        ["--count", "5", "--test-number", "invalid", "--test-number-amount", "1"],
    ]:
        with pytest.raises(SystemExit):
            parse_args(invalid)


def test_seed_defaults_to_empty_contact_and_assigns_exact_test_amount(connection):
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    seed_student_data(5, seed=42, session_factory=factory)
    with Session(connection) as db:
        assert len(db.scalars(select(Student)).all()) == 5
        assert db.scalars(select(Student.guardian_phone)).all() == [None] * 5

    seed_student_data(
        7,
        seed=43,
        test_number="081234567890",
        test_number_amount=3,
        session_factory=factory,
    )
    with Session(connection) as db:
        phones = db.scalars(select(Student.guardian_phone)).all()
        assert len(phones) == 12
        assert phones.count("081234567890") == 3
        assert phones.count(None) == 9
