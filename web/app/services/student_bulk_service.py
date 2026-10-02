from collections import Counter

from app.models.class_ import Class
from app.models.student import Student
from app.schemas.student import (
    StudentBulkCreateRequest,
    StudentBulkDeleteRequest,
    StudentBulkUpdateRequest,
    StudentResponse,
    StudentWriteRequest,
)
from app.services.exceptions import (
    AppException,
    ClassNotFound,
    DuplicateNisn,
    StudentNotFound,
)
from pydantic import ValidationError
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .helpers import bulk_response_or_422, check_missing_fields, fail
from .student_service import _normalize_guardian_phone, _save_student


def count_nisns(students) -> Counter:
    """Count NISN occurrences across a batch, for in-batch duplicate detection."""
    return Counter(student.nisn for student in students)


def class_id_is_valid(class_id: int | None, class_ids_db: set) -> bool:
    """A null class_id is always valid (unassigned); otherwise it must exist."""
    return class_id is None or class_id in class_ids_db


def validate_new_student(
    student: StudentBulkCreateRequest,
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

    try:
        StudentWriteRequest.model_validate(
            {
                **student.model_dump(),
                "current": student.current if student.current is not None else True,
            }
        )
    except ValidationError as exc:
        raise AppException("invalid student fields", 422) from exc

    if nisn_batch_counts[student.nisn] > 1:
        raise DuplicateNisn(detail="duplicate nisn in batch")

    if student.nisn in nisns_db:
        raise DuplicateNisn()

    if not class_id_is_valid(student.class_id, class_ids_db):
        raise ClassNotFound()


def create_students_bulk(
    db: Session, payload: list[StudentBulkCreateRequest], dry_run: bool
) -> dict:
    """Create one or more students in one transaction. Returns the
    succeeded/failed envelope never raises; per-item AppExceptions are
    caught here and folded into the failed list."""
    requested_nisns = {student.nisn for student in payload if student.nisn is not None}
    requested_classes = {
        student.class_id for student in payload if student.class_id is not None
    }
    nisns_db = set(
        db.scalars(select(Student.nisn).where(Student.nisn.in_(requested_nisns)))
    )
    class_ids_db = set(
        db.scalars(select(Class.class_id).where(Class.class_id.in_(requested_classes)))
    )
    nisn_batch_counts = count_nisns(payload)

    failed = []
    new_students_meta = []  # (index, Student) pairs pending insert
    new_students = []

    for index, student in enumerate(payload):
        try:
            validate_new_student(student, nisns_db, class_ids_db, nisn_batch_counts)
        except AppException as exc:
            failed.append(
                fail(index, exc.detail, student.model_dump(exclude_unset=True))
            )
            continue

        new_student = Student(
            name=student.name,
            nisn=student.nisn,
            class_id=student.class_id,
            current=student.current if student.current is not None else True,
            guardian_phone=_normalize_guardian_phone(student.guardian_phone),
        )
        new_students.append(new_student)
        new_students_meta.append((index, new_student))

    db.add_all(new_students)
    _save_student(db, commit=False)

    succeeded: list[dict] = []
    for index, new_student in new_students_meta:
        succeeded.append(
            {
                "index": index,
                "item": StudentResponse.model_validate(new_student).model_dump(),
            }
        )

    if dry_run:
        db.rollback()
    else:
        _save_student(db, commit=True)

    return bulk_response_or_422(succeeded, failed)


def validate_updated_student(
    student: StudentBulkUpdateRequest,
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

    if not class_id_is_valid(student.class_id, class_ids_db):
        raise ClassNotFound()


def update_students_bulk(
    db: Session, payload: list[StudentBulkUpdateRequest], dry_run: bool
) -> dict:
    """Update multiple students in a single transaction. Returns the
    succeeded/failed envelope never raises out; per-item AppExceptions
    are caught here."""

    # Simulates the transaction to avoid false collisions when swapping values
    before_transaction = dict(db.execute(select(Student.id, Student.nisn)).all())  # type: ignore
    nisns_payload = {student.id: student.nisn for student in payload}
    after_transaction = before_transaction | nisns_payload

    requested_ids = {student.id for student in payload if student.id is not None}
    stored = {
        row.id: row
        for row in db.execute(
            select(
                Student.id, Student.photo_path, Student.current, Student.guardian_phone
            ).where(Student.id.in_(requested_ids))
        )
    }
    student_ids_db = set(stored)
    id_counts = Counter(student.id for student in payload)
    requested_classes = {
        student.class_id for student in payload if student.class_id is not None
    }
    class_ids_db = set(
        db.scalars(select(Class.class_id).where(Class.class_id.in_(requested_classes)))
    )
    nisn_batch_counts = count_nisns(payload)
    nisn_counts_after_transaction = Counter(after_transaction.values())

    failed = []
    succeeded: list[dict] = []
    updating_students = []

    for index, student in enumerate(payload):
        try:
            if id_counts[student.id] > 1:
                raise AppException("duplicate id in batch", 422)
            validate_updated_student(
                student,
                student_ids_db,
                class_ids_db,
                nisn_batch_counts,
                nisn_counts_after_transaction,
            )
            StudentWriteRequest.model_validate(
                {
                    **student.model_dump(),
                    "current": student.current
                    if student.current is not None
                    else stored[student.id].current,
                }
            )
        except ValidationError:
            failed.append(
                fail(
                    index,
                    "invalid student fields",
                    student.model_dump(exclude_unset=True),
                )
            )
            continue
        except AppException as exc:
            failed.append(
                fail(index, exc.detail, student.model_dump(exclude_unset=True))
            )
            continue

        updating_student = {
            "id": student.id,
            "name": student.name,
            "nisn": student.nisn,
            "class_id": student.class_id,
            "current": student.current
            if student.current is not None
            else stored[student.id].current,
            "guardian_phone": _normalize_guardian_phone(student.guardian_phone)
            if "guardian_phone" in student.model_fields_set
            else stored[student.id].guardian_phone,
        }
        updating_students.append(updating_student)
        succeeded.append(
            {
                "index": index,
                "item": {
                    **updating_student,
                    "photo_path": stored[student.id].photo_path,
                },
            }
        )

    # Rejected rows retain their old NISNs. Removing one candidate can invalidate
    # another dependent swap, so validate the actual surviving state to a fixpoint.
    while succeeded:
        final = before_transaction | {
            entry["item"]["id"]: entry["item"]["nisn"] for entry in succeeded
        }
        counts = Counter(final.values())
        rejected = [entry for entry in succeeded if counts[entry["item"]["nisn"]] > 1]
        if not rejected:
            break
        rejected_indexes = {entry["index"] for entry in rejected}
        for entry in rejected:
            failed.append(
                fail(
                    entry["index"],
                    "duplicate_nisn",
                    payload[entry["index"]].model_dump(exclude_unset=True),
                )
            )
        succeeded = [
            entry for entry in succeeded if entry["index"] not in rejected_indexes
        ]
    updating_students = [
        {key: value for key, value in entry["item"].items() if key != "photo_path"}
        for entry in succeeded
    ]
    try:
        db.execute(text("SET CONSTRAINTS students_nisn_key DEFERRED"))
        if updating_students:
            db.execute(update(Student), updating_students)
        db.execute(text("SET CONSTRAINTS students_nisn_key IMMEDIATE"))
        db.rollback() if dry_run else db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppException(
            "Data berubah atau bertabrakan. Muat ulang dan coba lagi.", 409
        ) from exc

    failed.sort(key=lambda entry: entry["index"])

    return bulk_response_or_422(succeeded, failed)


def delete_students_bulk(
    db: Session, payload: StudentBulkDeleteRequest, dry_run: bool
) -> list[int] | None:
    """Deletes all given ids, or none at all if any id is missing
    (all-or-nothing, unlike create/update). Returns the list of missing
    ids if any were missing, or None on success the router translates
    that into the 422/204 response."""
    payload_ids = set(payload.ids)
    if not payload_ids:
        return None

    db_ids = set(db.scalars(select(Student.id).where(Student.id.in_(payload_ids))))
    missing_ids = sorted(payload_ids - db_ids)

    if missing_ids:
        return missing_ids

    if dry_run:
        db.rollback()
    else:
        db.execute(delete(Student).where(Student.id.in_(payload_ids)))
        db.commit()
    return None
