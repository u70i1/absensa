from __future__ import annotations

import argparse
import random

from app.db.session import SessionLocal
from app.models.class_ import Class
from app.models.student import Student
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


def parse_args() -> argparse.Namespace:
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
    args = parser.parse_args()
    if args.count < 0:
        parser.error("--count must be zero or greater")
    return args


def seed_student_data(count: int, seed: int | None = None) -> None:
    fake = Faker("id_ID")
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    with SessionLocal.begin() as db:
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
        for _ in range(count):
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
                )
            )
        db.add_all(students)

    print(f"Added {count} students across {len(CLASSES)} classes.")


if __name__ == "__main__":
    args = parse_args()
    seed_student_data(args.count, args.seed)
