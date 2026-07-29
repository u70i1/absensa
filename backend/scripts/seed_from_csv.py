

import csv
from pathlib import Path

from app.db.session import SessionLocal
from app.models.student import Student
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]  # Up 2 directory levels
STUDENTS_CSV = BACKEND_DIR / "mock" / "students.csv"


def seed() -> None:
    """
    Seed the now existing Postgres database with data with csv from demo version.
    You might need to modify this according to your csv file seed.
    """
    if not STUDENTS_CSV.exists():
        raise FileNotFoundError(
            f"{STUDENTS_CSV} does not exist! Please double check the filename"
        )
    with open(STUDENTS_CSV, "r") as students:
        csvreader = csv.DictReader(students)
        db = SessionLocal()

        student_count = 0

        for row in csvreader:
            stmt = select(Student).where(Student.nisn == row["nisn"])
            existing = db.scalars(stmt).first()
            if existing:
                print(
                    f"Student with NISN {row['nisn']} already exists with ID {existing.id}, skipping..."
                )
                continue

            student = Student(
                name=row["name"],
                class_=row["class"],
                nisn=row["nisn"],
            )

            db.add(student)
            student_count += 1

        db.commit()
        print(f"{student_count} student(s) have been added to the students table.")

        print("Closing connection...")
        db.close()

if __name__ == "__main__":
    seed()
