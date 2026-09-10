
from collections import Counter

from app.models.class_ import Class
from app.schemas.BulkClassRequest import (
    BulkClassIdOnly,
    BulkClassRequest,
    BulkClassRequestWithId,
)
from app.schemas.ClassResponse import ClassResponse
from app.services.exceptions import AppException, ClassNameTooLong, DuplicateClass
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from .helpers import bulk_response_or_422, check_missing_fields, fail

CLASS_NAME_MAX_LENGTH = 20


def count_class_keys(keys) -> Counter:
    """Count (grade, class_name) occurrences across a batch, for in-batch duplicate detection."""
    return Counter(keys)


def validate_new_class(
    class_: BulkClassRequest,
    class_keys_db: set,
    class_key_batch_counts: Counter,
) -> None:
    """Create-time checks, raising the FIRST AppException found.
    Mirrors validate_new_student's structure/ordering."""

    missing = check_missing_fields(
        required={"class_name", "grade"}, input=class_.model_dump()
    )
    if missing:
        raise AppException(
            detail=f"missing fields: {', '.join(missing)}", status_code=422
        )

    if len(class_.class_name) > CLASS_NAME_MAX_LENGTH:  # type: ignore
        raise ClassNameTooLong()

    key = (class_.grade, class_.class_name)

    if class_key_batch_counts[key] > 1:
        raise DuplicateClass(detail="duplicate class_name in batch")

    if key in class_keys_db:
        raise DuplicateClass()


def create_classes_bulk(
    db: Session, payload: list[BulkClassRequest], dry_run: bool
) -> dict:
    """Create one or more classes in one transaction. Returns the
    succeeded/failed envelope — never raises; per-item AppExceptions are
    caught here and folded into the failed list."""
    class_keys_db = {
        (grade, class_name)
        for grade, class_name in db.execute(
            select(Class.grade, Class.class_name)
        ).all()
    }
    class_key_batch_counts = count_class_keys(
        (class_.grade, class_.class_name) for class_ in payload
    )

    failed = []
    new_classes_meta = []  # (index, Class) pairs pending insert
    new_classes = []

    for index, class_ in enumerate(payload):
        try:
            validate_new_class(class_, class_keys_db, class_key_batch_counts)
        except AppException as exc:
            failed.append(fail(index, exc.detail, class_))
            continue

        new_class = Class(class_name=class_.class_name, grade=class_.grade)
        new_classes.append(new_class)
        new_classes_meta.append((index, new_class))

    db.add_all(new_classes)
    db.flush()

    succeeded = []
    for index, new_class in new_classes_meta:
        db.refresh(new_class)
        succeeded.append(
            {
                "index": index,
                "item": ClassResponse.model_validate(new_class).model_dump(),
            }
        )

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return bulk_response_or_422(succeeded, failed)


def validate_updated_class(
    class_: BulkClassRequestWithId,
    class_ids_db: set,
    effective_key: tuple,
    class_key_batch_counts: Counter,
    class_key_counts_after_transaction: Counter,
) -> None:
    """Update-time checks. Kept separate from validate_new_class for the same
    reason validate_updated_student is separate from validate_new_student —
    the after-transaction swap simulation has no create-time equivalent."""

    missing = check_missing_fields(
        required={"class_id", "class_name"}, input=class_.model_dump()
    )
    if missing:
        raise AppException(
            detail=f"missing fields: {', '.join(missing)}", status_code=422
        )

    if len(class_.class_name) > CLASS_NAME_MAX_LENGTH:  # type: ignore
        raise ClassNameTooLong()

    if class_.class_id not in class_ids_db:
        raise AppException(detail="cannot find class_id", status_code=422)

    if class_key_batch_counts[effective_key] > 1:
        raise DuplicateClass(detail="duplicate class_name in batch")

    if class_key_counts_after_transaction[effective_key] > 1:
        raise DuplicateClass()


def update_classes_bulk(
    db: Session, payload: list[BulkClassRequestWithId], dry_run: bool
) -> dict:
    """Update multiple classes in a single transaction. Returns the
    succeeded/failed envelope — never raises out; per-item AppExceptions
    are caught here."""

    # Simulates the transaction to avoid false collisions when swapping
    # values. Uniqueness is on (grade, class_name) together now, so both
    # are tracked per class_id.
    before_transaction = {
        class_id: (grade, class_name)
        for class_id, grade, class_name in db.execute(
            select(Class.class_id, Class.grade, Class.class_name)
        ).all()
    }
    class_ids_db = set(before_transaction)

    # Each row's (grade, class_name) after its own update -- a row that
    # omits "grade" keeps the class's current grade.
    effective_keys = {
        class_.class_id: (
            class_.grade
            if class_.grade is not None
            else before_transaction.get(class_.class_id, (None, None))[0],
            class_.class_name,
        )
        for class_ in payload
    }

    after_transaction = before_transaction | effective_keys
    class_key_batch_counts = count_class_keys(effective_keys.values())
    class_key_counts_after_transaction = Counter(after_transaction.values())

    failed = []
    succeeded = []
    updating_classes = []

    for index, class_ in enumerate(payload):
        try:
            validate_updated_class(
                class_,
                class_ids_db,
                effective_keys[class_.class_id],
                class_key_batch_counts,
                class_key_counts_after_transaction,
            )
        except AppException as exc:
            failed.append(fail(index, exc.detail, class_))
            continue

        grade, class_name = effective_keys[class_.class_id]
        updating_class = {
            "class_id": class_.class_id,
            "class_name": class_name,
            "grade": grade,
        }
        updating_classes.append(updating_class)
        succeeded.append({"index": index, "item": updating_class})

    db.execute(text("SET CONSTRAINTS uq_grade_class_name DEFERRED"))
    db.execute(update(Class), updating_classes)

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return bulk_response_or_422(succeeded, failed)


def delete_classes_bulk(
    db: Session, payload: BulkClassIdOnly, dry_run: bool
) -> list[int] | None:
    """Deletes all given ids, or none at all if any id is missing
    (all-or-nothing). Returns the list of missing ids if any were missing,
    or None on success — the router translates that into the 422/204 response."""
    payload_ids = set(payload.ids)
    if not payload_ids:
        return None

    db_ids = set(db.scalars(select(Class.class_id)).all())
    missing_ids = [i for i in payload_ids if i not in db_ids]

    if missing_ids:
        return missing_ids

    if dry_run:
        db.rollback()
    else:
        db.execute(delete(Class).where(Class.class_id.in_(payload_ids)))
    return None
