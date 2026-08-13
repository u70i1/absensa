from collections import Counter

from app.db.session import get_db
from app.models.class_ import Class
from app.models.student import Student
from app.schemas.BulkStudentRequest import BulkStudentRequest
from app.schemas.BulkStudentResponse import BulkStudentResponse
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/students/bulk", response_model=BulkStudentResponse)
def post_students_bulk(
    payload: list[BulkStudentRequest], db: Session = Depends(get_db)
):
    """Create students in bulk. Receives a list of StudentRequest."""
    succeeded = []
    failed = []
    REQUIRED_FIELDS = {"nisn", "name"}
    enum_payload = enumerate(payload)

    # Existing nisns and class_ids for checking
    existing_nisns_db = set(db.scalars(select(Student.nisn)).all())
    existing_class_ids = set(db.scalars(select(Class.class_id)).all())

    # Count nisn duplicates in the payload
    nisn_counter = Counter([student.nisn for student in payload])

    new_students = []
    for index, student in enum_payload:
        success = True

        provided = {
            field for field, value in student.model_dump().items() if value is not None
        }
        missing = REQUIRED_FIELDS - provided

        if missing:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": f"missing fields: {', '.join(missing)}",
                    "student": student,
                }
            )

        if nisn_counter[student.nisn] > 1:
            success = False
            failed.append(
                {"index": index, "error": "duplicate nisn in batch", "student": student}
            )
        # Check if NISN already exists
        if student.nisn in existing_nisns_db:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": "duplicate nisn",
                    "student": student,
                }
            )
        # Check if class_id actually exists
        if student.class_id is not None and student.class_id not in existing_class_ids:
            success = False
            failed.append(
                {"index": index, "error": "class_id does not exist", "student": student}
            )

        # After checks, attempts to add students
        if success:
            new_student = Student(
                name=student.name,
                nisn=student.nisn,
                class_id=student.class_id,
                current=student.current,
            )
            new_students.append(new_student)
            succeeded.append({"index": index, "student": new_student})

    db.add_all(new_students)
    db.commit()

    return {
        "succeeded": succeeded,
        "failed": failed,
    }
