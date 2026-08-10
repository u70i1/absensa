from pathlib import Path

from app.db.session import SessionLocal
from app.models.class_ import Class
from app.models.student import Student
from sqlalchemy import select

SEED_CLASS = [
    {"class_name": "X-Mossy"},
    {"class_name": "X-Bottom"},
    {"class_name": "XI-Flock"},
    {"class_name": "XI-Barn"},
    {"class_name": "XII-Farm"},
]

SEED_STUDENT = [
    {"name": "Shaun", "nisn": "1000000001", "class_name": "X-Mossy"},
    {"name": "Bitzer", "nisn": "1000000002", "class_name": "X-Mossy"},
    {"name": "Shirley", "nisn": "1000000003", "class_name": "X-Mossy"},
    {"name": "Timmy", "nisn": "1000000004", "class_name": "X-Bottom"},
    {"name": "Hazel", "nisn": "1000000005", "class_name": "X-Bottom"},
    {"name": "Nuts", "nisn": "1000000006", "class_name": "X-Bottom"},
    {"name": "Slip", "nisn": "1000000009", "class_name": "XI-Flock"},
    {"name": "Pidsley", "nisn": "1000000010", "class_name": "XI-Barn"},
    {"name": "Lexi", "nisn": "1000000011", "class_name": "XI-Barn"},
    {"name": "Jin", "nisn": "1000000012", "class_name": "XI-Barn"},
    {"name": "Hector", "nisn": "1000000013", "class_name": "XII-Farm"},
    {"name": "Raul", "nisn": "1000000014", "class_name": "XII-Farm"},
    {
        "name": "Lola",
        "nisn": "1000000015",
        "class_name": "XII-Mossy",
        "current": False,
    },
    {
        "name": "Trumper",
        "nisn": "1000000016",
        "class_name": None,
    },
]


def seed() -> None:
    with SessionLocal() as db:
        # Insert classes
        print("Adding classes")
        classes = []
        for c in SEED_CLASS:
            classes.append(Class(class_name=c["class_name"]))

        db.add_all(classes)
        db.flush()

        # Insert students
        print("Adding students")
        students = []
        for student in SEED_STUDENT:
            class_id = db.scalar(
                select(Class.class_id).where(Class.class_name == student.get("class_name"))
            )
            students.append(
                Student(
                    name=student["name"],
                    class_id=class_id,
                    nisn=student["nisn"],
                    current=student.get("current", True),
                )
            )

        db.add_all(students)
        db.commit()

        print("Done!")


if __name__ == "__main__":
    seed()
