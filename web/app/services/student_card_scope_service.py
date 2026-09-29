"""Validate bulk card scopes before any rendering or download begins."""

from app.models.student import Student
from app.services.exceptions import AppException
from app.services.student_dashboard_service import dashboard_context
from app.services.table_selection_service import MAX_SELECTION_SIZE
from sqlalchemy import select


def resolve_students(db, scope, raw_ids, query, *, confirmed=False, page_ids=()):
    if scope == "all":
        if not confirmed:
            raise AppException(
                "Konfirmasi diperlukan untuk memproses semua siswa. Operasi ini memerlukan banyak sumber daya dan waktu; gunakan hanya bila diperlukan.",
                422,
            )
        # A server-side cursor avoids retaining all ORM objects during export.
        students = db.scalars(
            select(Student).order_by(Student.id).execution_options(yield_per=50)
        )
        return students
    if scope not in {"page", "selected"}:
        raise AppException("Cakupan kartu tidak valid.", 422)
    raw = page_ids if scope == "page" else raw_ids
    try:
        ids = sorted({int(value) for value in raw})
    except (TypeError, ValueError):
        raise AppException("Pilihan siswa tidak valid.", 422) from None
    if not ids or len(ids) > MAX_SELECTION_SIZE or ids[0] < 1 or ids[-1] > 2147483647:
        raise AppException("Pilih siswa untuk melanjutkan.", 422)
    if scope == "page":
        visible = sorted(
            student.id for student in dashboard_context(db, query)["students"]
        )
        if ids != visible:
            raise AppException(
                "Daftar siswa berubah. Muat ulang halaman sebelum mencetak.", 409
            )
    students = list(
        db.scalars(select(Student).where(Student.id.in_(ids)).order_by(Student.id))
    )
    if len(students) != len(ids):
        raise AppException(
            "Sebagian siswa sudah dihapus. Muat ulang daftar dan pilih kembali.", 409
        )
    return students
