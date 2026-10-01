"""Validate dashboard selections for exports and atomic mutations."""

from app.models.class_ import Class
from app.models.scan_log import ScanLog
from app.models.student import Student
from app.schemas.student import StudentListQuery
from app.services import student_service
from app.services.exceptions import AppException
from sqlalchemy import delete, select, update

MAX_SELECTION_SIZE = 1000
MODEL_KEYS = {
    "students": (Student, Student.id),
    "classes": (Class, Class.class_id),
    "scans": (ScanLog, ScanLog.scan_id),
}


def selected_records(db, kind, action, raw_ids, *, lock=False):
    actions = {
        "students": {"delete", "deactivate", "export"},
        "classes": {"delete", "export"},
        "scans": {"delete"},
    }
    if kind not in MODEL_KEYS or action not in actions[kind]:
        raise AppException("Tindakan tidak valid.", 422)
    try:
        ids = sorted({int(value) for value in raw_ids})
    except (TypeError, ValueError):
        raise AppException("Pilihan tidak valid.", 422) from None
    if not ids or len(ids) > MAX_SELECTION_SIZE or ids[0] < 1:
        raise AppException("Pilih 1–1000 data untuk melanjutkan.", 422)
    model, key = MODEL_KEYS[kind]
    statement = select(model).where(key.in_(ids)).order_by(key)
    if lock:
        statement = statement.with_for_update()
    records = list(db.scalars(statement))
    if len(records) != len(ids):
        raise AppException(
            "Sebagian data sudah dihapus. Muat ulang daftar dan pilih kembali.", 409
        )
    return records


def selection_export_data(db, kind, raw_ids):
    """Export the whole retained selection, including rows outside current filters."""
    records = selected_records(db, kind, "export", raw_ids)
    ids = [record.id if kind == "students" else record.class_id for record in records]
    students = student_service.get_students_for_export(
        db,
        StudentListQuery(),
        **{"student_ids" if kind == "students" else "class_ids": ids},
    )
    if kind == "students":
        scope = f"{len(records)} siswa terpilih"
    else:
        names = ", ".join(f"{record.grade} / {record.class_name}" for record in records)
        scope = f"Siswa dari {len(records)} kelas terpilih: {names}"
    return records, students, scope


def apply_selection(db, kind, action, raw_ids):
    if action not in {"delete", "deactivate"}:
        raise AppException("Tindakan tidak valid.", 422)
    try:
        records = selected_records(db, kind, action, raw_ids, lock=True)
        model, key = MODEL_KEYS[kind]
        ids = [getattr(record, key.key) for record in records]
        if action == "deactivate":
            db.execute(update(Student).where(Student.id.in_(ids)).values(current=False))
        else:
            db.execute(delete(model).where(key.in_(ids)))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(records)
