"""Seed student records for local development."""

from __future__ import annotations

import argparse
import random

from app.db.session import SessionLocal
from app.models.class_ import Class
from app.models.student import Student
from app.schemas.student import normalize_guardian_phone
from app.services.whatsapp_gateway_service import GatewayProblem
from app.services.whatsapp_notification_service import guardian_recipient
from faker import Faker
from sqlalchemy import select

CLASSES = (
    (7, "VII-A"),
    (7, "VII-B"),
    (7, "VII-C"),
    (7, "VII-D"),
    (7, "VII-E"),
    (7, "VII-F"),
    (7, "VII-G"),
    (8, "VIII-A"),
    (8, "VIII-B"),
    (8, "VIII-C"),
    (8, "VIII-D"),
    (8, "VIII-E"),
    (9, "IX-A"),
    (9, "IX-B"),
    (9, "IX-C"),
    (9, "IX-D"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=int,
        default=500,
        help="number of students to add (default: 500)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="random seed for repeatable generated names and assignments",
    )
    parser.add_argument(
        "--test-number",
        help="one guardian number to assign to selected new students (08 or 628 format)",
    )
    parser.add_argument(
        "--test-number-amount",
        type=int,
        default=0,
        help="number of new students receiving --test-number (default: 0)",
    )
    args = parser.parse_args(argv)
    if args.count < 0:
        parser.error("--count must be zero or greater")
    if args.test_number_amount < 0 or args.test_number_amount > args.count:
        parser.error("--test-number-amount must be between zero and --count")
    if bool(args.test_number) != bool(args.test_number_amount):
        parser.error(
            "--test-number and a positive --test-number-amount must be used together"
        )
    if args.test_number:
        try:
            args.test_number = normalize_guardian_phone(args.test_number)
            guardian_recipient(args.test_number)
        except ValueError:
            parser.error("--test-number must use digits and begin with 08 or 628")
        except GatewayProblem:
            parser.error("--test-number must be a usable international-length number")
    return args


def seed_student_data(
    count: int,
    seed: int | None = None,
    test_number: str | None = None,
    test_number_amount: int = 0,
    session_factory=None,
) -> None:
    fake = Faker("id_ID")
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    session_factory = session_factory or SessionLocal
    with session_factory.begin() as db:
        existing_classes = {
            (class_.grade, class_.class_name): class_
            for class_ in db.scalars(select(Class)).all()
        }
        classes = []
        for grade, class_name in CLASSES:
            class_ = existing_classes.get((grade, class_name))
            if class_ is None:
                class_ = Class(grade=grade, class_name=class_name)
                db.add(class_)
            classes.append(class_)
        db.flush()

        used_nisns = set(db.scalars(select(Student.nisn)).all())
        students = []
        test_indices = set(random.sample(range(count), test_number_amount))
        for index in range(count):
            nisn = fake.numerify(text="##########")
            while nisn in used_nisns:
                nisn = fake.numerify(text="##########")
            used_nisns.add(nisn)
            class_ = random.choice(classes)
            students.append(
                Student(
                    name=fake.name(),
                    nisn=nisn,
                    class_id=class_.class_id,
                    current=True,
                    guardian_phone=test_number if index in test_indices else None,
                )
            )
        db.add_all(students)

    print(f"Added {count} students across {len(CLASSES)} classes.")


if __name__ == "__main__":
    args = parse_args()
    seed_student_data(args.count, args.seed, args.test_number, args.test_number_amount)
