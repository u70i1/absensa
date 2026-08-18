from collections import Counter

from app.db.session import get_db
from app.models.class_ import Class
from app.models.student import Student
from app.schemas.BulkStudentRequest import (
    BulkStudentIdOnly,
    BulkStudentRequest,
    BulkStudentRequestWithId,
)
from app.schemas.BulkStudentResponse import BulkStudentResponse
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

router = APIRouter()


@router.post(
    "/students/bulk",
    response_model=BulkStudentResponse,
    responses={
        422: {"description": "All items failed"},
    },
)
def post_students_bulk(
    payload: list[BulkStudentRequest], db: Session = Depends(get_db)
):
    """Create one or more students item in one request."""
    succeeded = []
    failed = []
    enum_payload = enumerate(payload)
    REQUIRED_FIELDS = {"nisn", "name"}

    # Existing nisns and class_ids for checking
    nisns_db = set(db.scalars(select(Student.nisn)).all())
    class_ids_db = set(db.scalars(select(Class.class_id)).all())

    # Count nisn duplicates in the payload
    nisn_payload_counter = Counter([student.nisn for student in payload])

    new_students = []
    new_students_meta = []
    for index, student in enum_payload:
        success = True

        # Manually validate fields to prevent HTTP 422 for all items
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

        if nisn_payload_counter[student.nisn] > 1:
            success = False
            failed.append(
                {"index": index, "error": "duplicate nisn in batch", "student": student}
            )

        if student.nisn in nisns_db:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": "duplicate nisn",
                    "student": student,
                }
            )

        if student.class_id is not None and student.class_id not in class_ids_db:
            success = False
            failed.append(
                {"index": index, "error": "class_id does not exist", "student": student}
            )

        # After checks, attempts to add student
        if success:
            new_student = Student(
                name=student.name,
                nisn=student.nisn,
                class_id=student.class_id,
                current=student.current,
            )
            new_students.append(new_student)
            new_students_meta.append((index, new_student))

    db.add_all(new_students)
    db.commit()

    # This ensures consistency between the database and response
    for index, new_student in new_students_meta:
        db.refresh(new_student)
        succeeded.append(
            {
                "index": index,
                "student": new_student,
            }
        )
    response = {
        "succeeded": succeeded,
        "failed": failed,
    }

    if len(new_students_meta) < 1 and len(failed) >= 1:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(response),
        )

    return response


@router.put("/students/bulk", response_model=BulkStudentResponse)
def update_students_bulk(
    payload: list[BulkStudentRequestWithId], db: Session = Depends(get_db)
):
    """Update multiple students in single request."""

    succeeded = []
    failed = []
    enum_payload = enumerate(payload)
    REQUIRED_FIELDS = {"id", "nisn", "name"}

    # Simulates the transaction to avoid false collisions when swapping values
    before_transaction = dict(db.execute(select(Student.id, Student.nisn)).all())  # type: ignore
    nisns_payload = {student.id: student.nisn for student in payload}
    after_transaction = before_transaction | nisns_payload

    student_ids_db = set(db.scalars(select(Student.id)).all())
    class_ids_db = set(db.scalars(select(Class.class_id)).all())

    nisn_counter_payload = Counter(student.nisn for student in payload)
    nisn_counter_after_transaction = Counter(
        nisn for nisn in after_transaction.values()
    )

    updating_students = []
    for index, student in enum_payload:
        success = True

        # Manually handle missing fields to prevent HTTP 422 for all items
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

        if student.id not in student_ids_db:
            success = False
            failed.append(
                {"index": index, "error": "cannot find the id", "student": student}
            )

        if nisn_counter_payload[student.nisn] > 1:
            success = False
            failed.append(
                {"index": index, "error": "duplicate nisn in batch", "student": student}
            )

        if nisn_counter_after_transaction[student.nisn] > 1:
            success = False
            failed.append(
                {
                    "index": index,
                    "error": "duplicate nisn",
                    "student": student,
                }
            )
        # Check if class_id actually exists
        if student.class_id is not None and student.class_id not in class_ids_db:
            success = False
            failed.append(
                {"index": index, "error": "class_id does not exist", "student": student}
            )

        if success:
            updating_student = {
                "id": student.id,
                "name": student.name,
                "nisn": student.nisn,
                "class_id": student.class_id,
                "current": student.current,
            }
            updating_students.append(updating_student)
            succeeded.append(
                {
                    "index": index,
                    "student": updating_student,
                }
            )

    db.execute(text("SET CONSTRAINTS students_nisn_key DEFERRED"))
    db.execute(update(Student), updating_students)
    db.commit()

    if len(succeeded) < 1 and len(failed) >= 1:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "succeeded": succeeded,
                    "failed": failed,
                }
            ),
        )

    return {
        "succeeded": succeeded,
        "failed": failed,
    }


@router.post("/students/bulk-delete", status_code=204)
def delete_students_bulk(payload: BulkStudentIdOnly, db: Session = Depends(get_db)):
    payload_ids = set(payload.ids)
    if not payload_ids:
        return

    db_ids = set(db.scalars(select(Student.id)).all())

    missing_ids = []
    for i in payload_ids:
        if i in db_ids:
            continue
        missing_ids.append(i)
    if len(missing_ids) >= 1:
        return JSONResponse(
            status_code=422, content=jsonable_encoder({"missing_ids": missing_ids})
        )

    db.execute(delete(Student).where(Student.id.in_(payload_ids)))
