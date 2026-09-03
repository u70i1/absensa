from collections import Counter

from app.models.class_ import Class
from app.models.student import Student
from app.schemas.BulkStudentRequest import (
    BulkStudentIdOnly,
    BulkStudentRequest,
    BulkStudentRequestWithId,
)
from app.services.exceptions import (
    AppException,
    ClassNotFound,
    DuplicateNisn,
    StudentNotFound,
)
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from .helpers import bulk_response_or_422, check_missing_fields, fail


def count_nisns(students) -> Counter:
    """Count NISN occurrences across a batch, for in-batch duplicate detection."""
    return Counter(student.nisn for student in students)


def class_id_is_valid(class_id: int | None, class_ids_db: set) -> bool:
    """A null class_id is always valid (unassigned); otherwise it must exist."""
    return class_id is None or class_id in class_ids_db


def validate_new_student(
    student: BulkStudentRequest,
    nisns_db: set,
    class_ids_db: set,
    nisn_batch_counts: Counter,
) -> None:
    """Runs every create-time check, raising the FIRST AppException found.
    Returns None if the student is valid. Mirrors the original's checks 1:1
    only the signaling mechanism changed (raise instead of return-a-dict)."""

    missing = check_missing_fields(
        required={"nisn", "name"}, input=student.model_dump()
    )
    if missing:
        raise AppException(
            detail=f"missing fields: {', '.join(missing)}", status_code=422
        )

    if nisn_batch_counts[student.nisn] > 1:
        raise DuplicateNisn(detail="duplicate nisn in batch")

    if student.nisn in nisns_db:
        raise DuplicateNisn()

    if not class_id_is_valid(student.class_id, class_ids_db):
        raise ClassNotFound()


def create_students_bulk(db: Session, payload: list[BulkStudentRequest]) -> dict:
    """Create one or more students in one transaction. Returns the
    succeeded/failed envelope never raises; per-item AppExceptions are
    caught here and folded into the failed list."""
    nisns_db = set(db.scalars(select(Student.nisn)).all())
    class_ids_db = set(db.scalars(select(Class.class_id)).all())
    nisn_batch_counts = count_nisns(payload)

    failed = []
    new_students_meta = []  # (index, Student) pairs pending insert
    new_students = []

    for index, student in enumerate(payload):
        try:
            validate_new_student(student, nisns_db, class_ids_db, nisn_batch_counts)
        except AppException as exc:
            failed.append(fail(index, exc.detail, student))
            continue

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

    # Refresh after commit so the response includes DB-generated fields (e.g. id)
    succeeded = []
    for index, new_student in new_students_meta:
        db.refresh(new_student)
        succeeded.append({"index": index, "item": new_student})

    return bulk_response_or_422(succeeded, failed)


def validate_updated_student(
    student: BulkStudentRequestWithId,
    student_ids_db: set,
    class_ids_db: set,
    nisn_batch_counts: Counter,
    nisn_counts_after_transaction: Counter,
) -> None:
    """Update-time checks. Kept separate from validate_new_student because the
    nisn-swap simulation (before/after transaction) has no equivalent on create
    forcing them into one shared function would mean branching on "is this a
    create or update" inside the validator, which hides the difference rather
    than expressing it."""

    missing = check_missing_fields(
        required={"id", "nisn", "name"}, input=student.model_dump()
    )
    if missing:
        raise AppException(
            detail=f"missing fields: {', '.join(missing)}", status_code=422
        )

    if student.id not in student_ids_db:
        raise StudentNotFound(detail="cannot find the id")

    if nisn_batch_counts[student.nisn] > 1:
        raise DuplicateNisn(detail="duplicate nisn in batch")

    if nisn_counts_after_transaction[student.nisn] > 1:
        raise DuplicateNisn()

    if not class_id_is_valid(student.class_id, class_ids_db):
        raise ClassNotFound()


def update_students_bulk(db: Session, payload: list[BulkStudentRequestWithId]) -> dict:
    """Update multiple students in a single transaction. Returns the
    succeeded/failed envelope never raises out; per-item AppExceptions
    are caught here."""

    # Simulates the transaction to avoid false collisions when swapping values
    before_transaction = dict(db.execute(select(Student.id, Student.nisn)).all())  # type: ignore
    nisns_payload = {student.id: student.nisn for student in payload}
    after_transaction = before_transaction | nisns_payload

    student_ids_db = set(db.scalars(select(Student.id)).all())
    class_ids_db = set(db.scalars(select(Class.class_id)).all())
    nisn_batch_counts = count_nisns(payload)
    nisn_counts_after_transaction = Counter(after_transaction.values())

    failed = []
    succeeded = []
    updating_students = []

    for index, student in enumerate(payload):
        try:
            validate_updated_student(
                student,
                student_ids_db,
                class_ids_db,
                nisn_batch_counts,
                nisn_counts_after_transaction,
            )
        except AppException as exc:
            failed.append(fail(index, exc.detail, student))
            continue

        updating_student = {
            "id": student.id,
            "name": student.name,
            "nisn": student.nisn,
            "class_id": student.class_id,
            "current": student.current,
        }
        updating_students.append(updating_student)
        succeeded.append({"index": index, "item": updating_student})

    db.execute(text("SET CONSTRAINTS students_nisn_key DEFERRED"))
    db.execute(update(Student), updating_students)
    db.commit()

    return bulk_response_or_422(succeeded, failed)


def delete_students_bulk(db: Session, payload: BulkStudentIdOnly) -> list[int] | None:
    """Deletes all given ids, or none at all if any id is missing
    (all-or-nothing, unlike create/update). Returns the list of missing
    ids if any were missing, or None on success the router translates
    that into the 422/204 response."""
    payload_ids = set(payload.ids)
    if not payload_ids:
        return None

    db_ids = set(db.scalars(select(Student.id)).all())
    missing_ids = [i for i in payload_ids if i not in db_ids]

    if missing_ids:
        return missing_ids

    db.execute(delete(Student).where(Student.id.in_(payload_ids)))
    return None
