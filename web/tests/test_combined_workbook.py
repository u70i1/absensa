"""Class dictionary, protected identities, rename resolution and atomic writes."""

from io import BytesIO

import pytest
from app.models.class_ import Class
from app.models.student import Student
from app.services import export_service, import_service
from app.services.exceptions import AppException
from openpyxl import load_workbook
from sqlalchemy import event, select, text

from tests.test_import import importer  # noqa: F401


def save(book):
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def workbook(db, students=()):
    return load_workbook(
        BytesIO(
            export_service.build_students_workbook(
                students,
                "Jenjang 11",
                db.scalars(select(Class).order_by(Class.class_id)),
            )
        )
    )


def student_row(
    sheet,
    row,
    *,
    id=None,
    name="New student",
    class_id=None,
    nisn="0000000001",
    grade=None,
    class_name=None,
):
    for column, value in enumerate(
        (id, name, nisn, "Aktif", None, grade, class_name, class_id), 1
    ):
        sheet.cell(row, column).value = value


def preview(db, admin, book):
    return import_service.create_preview(
        db, admin.id, None, "combined.xlsx", BytesIO(save(book))
    )


def apply(db, admin, batch):
    return import_service.apply_preview(
        db, admin.id, batch.token, [r["key"] for r in batch.payload["rows"]]
    )


def snapshot(db):
    db.expire_all()
    return (
        list(
            db.execute(
                select(
                    Student.id,
                    Student.name,
                    Student.class_id,
                    Student.nisn,
                    Student.current,
                    Student.guardian_phone,
                ).order_by(Student.id)
            )
        ),
        list(
            db.execute(
                select(Class.class_id, Class.grade, Class.class_name).order_by(
                    Class.class_id
                )
            )
        ),
    )


@pytest.mark.parametrize(
    "mode",
    [
        "unchanged",
        "rename_old_text",
        "rename_final_text",
        "rename_grade",
        "reassign",
        "new_declared",
        "swap_names",
    ],
)
def test_relationship_resolution(
    db_session, importer, existing_student, class_factory, student_factory, mode
):
    db, student = db_session, existing_student
    original_id = student.class_id
    other = class_factory(grade=12, class_name="Other")
    # This student is not exported but must also follow its class relationship.
    omitted = student_factory(nisn="9999999999", class_id=original_id)
    book = workbook(db, [student])
    sheet = book["students"]
    expected_id, expected_pair = original_id, (11, "11B")
    if mode.startswith("rename"):
        expected_pair = (9 if mode == "rename_grade" else 11, "Renamed")
        book["classes"]["B2"], book["classes"]["C2"] = expected_pair
        if mode == "rename_final_text":
            sheet["F2"], sheet["G2"] = expected_pair
    elif mode == "reassign":
        sheet["F2"], sheet["G2"] = 12, "Other"
        expected_id, expected_pair = other.class_id, (12, "Other")
    elif mode == "new_declared":
        book["classes"]["B4"], book["classes"]["C4"] = 6, "New"
        sheet["F2"], sheet["G2"] = 6, "New"
        expected_id, expected_pair = None, (6, "New")
    elif mode == "swap_names":
        book["classes"]["B2"], book["classes"]["C2"] = 12, "Other"
        book["classes"]["B3"], book["classes"]["C3"] = 11, "11B"
        expected_pair = (12, "Other")
    batch = preview(db, importer, book)
    assert not batch.payload["errors"]
    apply(db, importer, batch)
    db.refresh(student)
    if expected_id is not None:
        assert student.class_id == expected_id
    assigned = db.get(Class, student.class_id)
    assert (assigned.grade, assigned.class_name) == expected_pair
    assert len(list(db.scalars(select(Class)))) == (3 if mode == "new_declared" else 2)
    fresh = workbook(db, [student, omitted])
    assert (
        fresh["students"]["F2"].value,
        fresh["students"]["G2"].value,
    ) == expected_pair
    assert fresh["students"]["H2"].value == student.class_id
    if mode.startswith("rename"):
        assert (
            fresh["students"]["F3"].value,
            fresh["students"]["G3"].value,
        ) == expected_pair
        assert fresh["students"]["H3"].value == original_id


@pytest.mark.parametrize("count", [1, 3])
def test_only_declared_new_class_is_created_once(db_session, importer, count):
    book = workbook(db_session)
    book["classes"]["B2"], book["classes"]["C2"] = 4, "New"
    for row in range(2, count + 2):
        student_row(book["students"], row, nisn=f"{row:010}", grade=4, class_name="New")
    batch = preview(db_session, importer, book)
    assert not batch.payload["errors"]
    apply(db_session, importer, batch)
    classes = list(db_session.scalars(select(Class)))
    students = list(db_session.scalars(select(Student)))
    assert len(classes) == 1 and len(students) == count
    assert {s.class_id for s in students} == {classes[0].class_id}


@pytest.mark.parametrize(
    "failure,cell",
    [
        ("undeclared_new", "3:G"),
        ("undeclared_reassignment", "2:G"),
        ("db_class_omitted", "2:G"),
        ("missing_grade", "2:F"),
        ("missing_name", "2:G"),
        ("new_no_class", "3:F"),
        ("invalid_grade", "2:F"),
        ("tampered_metadata", "2:H"),
        ("missing_metadata", "2:H"),
        ("new_with_metadata", "3:H"),
        ("duplicate_pair", "3:C"),
        ("duplicate_class_id", "3:A"),
        ("unknown_class_id", "2:A"),
        ("invalid_class", "2:B"),
        ("invalid_student", "3:C"),
        ("unknown_student", "2:A"),
        ("duplicate_student", "3:A"),
        ("missing_sheet", "1:A"),
        ("renamed_header", "1:G"),
        ("missing_header", "1:H"),
        ("formula", "2:F"),
    ],
)
def test_invalid_workbook_has_zero_effect(
    db_session, importer, existing_student, class_factory, failure, cell
):
    db = db_session
    other = class_factory(grade=12, class_name="Other")
    before = snapshot(db)
    book = workbook(db, [existing_student])
    s, c = book["students"], book["classes"]
    s["B2"] = "Valid student update"
    c["C2"] = "Valid rename"
    c["B4"], c["C4"] = 5, "Valid new class"
    if failure == "undeclared_new":
        student_row(s, 3, grade=5, class_name="Typo")
    elif failure == "undeclared_reassignment":
        s["F2"], s["G2"] = 5, "Typo"
    elif failure == "db_class_omitted":
        c.delete_rows(3)
        s["F2"], s["G2"] = 12, "Other"
    elif failure == "missing_grade":
        s["F2"] = None
    elif failure == "missing_name":
        s["G2"] = None
    elif failure == "new_no_class":
        student_row(s, 3)
    elif failure == "invalid_grade":
        s["F2"] = 21
    elif failure == "tampered_metadata":
        s["H2"] = other.class_id
    elif failure == "missing_metadata":
        s["H2"] = None
    elif failure == "new_with_metadata":
        student_row(s, 3, class_id=other.class_id, grade=12, class_name="Other")
    elif failure == "duplicate_pair":
        c["B3"], c["C3"] = c["B2"].value, c["C2"].value
    elif failure == "duplicate_class_id":
        c["A3"] = c["A2"].value
    elif failure == "unknown_class_id":
        c["A2"] = 2147483647
    elif failure == "invalid_class":
        c["B2"] = "invalid"
    elif failure == "invalid_student":
        student_row(s, 3, nisn="invalid", grade=5, class_name="Valid new class")
    elif failure == "unknown_student":
        s["A2"] = 2147483647
    elif failure == "duplicate_student":
        for col in range(1, 9):
            s.cell(3, col).value = s.cell(2, col).value
    elif failure == "missing_sheet":
        del book["classes"]
    elif failure == "renamed_header":
        s["G1"] = "Other"
    elif failure == "missing_header":
        s["H1"] = None
    elif failure == "formula":
        s["F2"] = "=11"
    batch = preview(db, importer, book)
    assert cell in {e["cell"] for e in batch.payload["errors"]}
    assert snapshot(db) == before
    with pytest.raises(AppException) as error:
        apply(db, importer, batch)
    assert error.value.status_code == 422
    assert snapshot(db) == before


def test_deleted_class_row_does_not_delete_database_class(
    db_session, importer, existing_student, class_factory
):
    other = class_factory(grade=12, class_name="Keep me")
    book = workbook(db_session, [existing_student])
    book["classes"].delete_rows(3)
    batch = preview(db_session, importer, book)
    assert not batch.payload["errors"]
    apply(db_session, importer, batch)
    assert db_session.get(Class, other.class_id).class_name == "Keep me"


@pytest.mark.parametrize("stage", ["student_write", "commit", "constraint"])
def test_runtime_failure_rolls_back_everything(
    db_session, importer, existing_student, monkeypatch, stage
):
    db = db_session
    before = snapshot(db)
    book = workbook(db, [existing_student])
    book["classes"]["C2"] = "Renamed"
    book["classes"]["B3"], book["classes"]["C3"] = 5, "New"
    book["students"]["B2"] = "Changed"
    student_row(book["students"], 3, grade=5, class_name="New")
    batch = preview(db, importer, book)
    assert not batch.payload["errors"]
    original = import_service._apply_student

    def fail_write(db, student_id, values):
        if stage == "constraint" and student_id is None:
            values["nisn"] = existing_student.nisn
        result = original(db, student_id, values)
        if stage == "student_write" and student_id is None:
            raise AppException("Kegagalan penyimpanan", 503)
        return result

    def fail_commit(session):
        session.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(import_service, "_apply_student", fail_write)
    if stage == "commit":
        event.listen(db, "before_commit", fail_commit)
    try:
        with pytest.raises(AppException):
            apply(db, importer, batch)
    finally:
        if stage == "commit":
            event.remove(db, "before_commit", fail_commit)
    assert snapshot(db) == before
    db.refresh(batch)
    assert batch.state == "pending"


def test_filtered_export_protects_ids_and_uses_class_dictionary(
    client, importer, existing_student, class_factory
):
    other = class_factory(grade=3, class_name="Different grade")
    response = client.get("/admin/students/export?grade=11")
    assert response.status_code == 200
    book = load_workbook(BytesIO(response.content))
    assert book.sheetnames == ["instructions", "students", "classes"]
    s, c = book["students"], book["classes"]
    assert s["A2"].value == existing_student.id and s["A3"].value is None
    assert [s.cell(2, col).value for col in (6, 7, 8)] == [
        11,
        "11B",
        existing_student.class_id,
    ]
    assert s.column_dimensions["H"].hidden and s.protection.sheet
    assert s["H2"].protection.locked and s["H3"].protection.locked
    assert (
        s["A2"].protection.locked and c["A2"].protection.locked and c.protection.sheet
    )
    for cell in ("B2", "F2", "G2", "B3", "F3", "G3"):
        assert not s[cell].protection.locked
    for cell in ("B2", "C2", "B3", "C3"):
        assert not c[cell].protection.locked
    ids = {r[0] for r in c.iter_rows(min_row=2, max_col=3, values_only=True)}
    assert {existing_student.class_id, other.class_id} <= ids
    assert "class_ids" not in book.defined_names
    assert {"jenjang_list", "kelas_3", "kelas_11"} <= set(book.defined_names)
    dvs = s.data_validations.dataValidation
    assert not any("H2" in dv.sqref for dv in dvs)
    assert any("F2" in dv.sqref and dv.formula1 == "jenjang_list" for dv in dvs)
    assert any(
        "G2" in dv.sqref and dv.formula1 == 'INDIRECT("kelas_"&$F2)' for dv in dvs
    )
    assert c.column_dimensions["E"].hidden
    source = load_workbook(export_service.STUDENT_TEMPLATE)
    assert s["B1"].fill.fgColor.rgb == source["students"]["B1"].fill.fgColor.rgb
    template = load_workbook(
        BytesIO(client.get("/admin/import/template/students").content)
    )
    assert template["students"]["A2"].value is None
    assert len({template["classes"]["A2"].value, template["classes"]["A3"].value}) == 2
    assert client.get("/admin/import/template/classes").status_code != 200
    assert client.get("/admin/classes/export").status_code != 200


@pytest.mark.parametrize("assigned", [False, True])
def test_existing_student_can_be_unassigned(
    db_session, importer, existing_student, assigned
):
    if not assigned:
        existing_student.class_id = None
        db_session.commit()
    book = workbook(db_session, [existing_student])
    book["students"]["F2"], book["students"]["G2"] = None, None
    batch = preview(db_session, importer, book)
    assert not batch.payload["errors"]
    apply(db_session, importer, batch)
    db_session.refresh(existing_student)
    assert existing_student.class_id is None


def test_invalid_existing_student_blocks_valid_student_and_class_changes(
    db_session, importer, existing_student, student_factory
):
    invalid = student_factory(nisn="9999999999", class_id=existing_student.class_id)
    before = snapshot(db_session)
    book = workbook(db_session, [existing_student, invalid])
    book["students"]["B2"] = "Valid update"
    book["students"]["C3"] = "invalid NISN"
    book["classes"]["C2"] = "Valid rename"
    book["classes"]["B3"], book["classes"]["C3"] = 6, "Valid new class"
    batch = preview(db_session, importer, book)
    assert any(e["cell"] == "3:C" for e in batch.payload["errors"])
    with pytest.raises(AppException):
        apply(db_session, importer, batch)
    assert snapshot(db_session) == before


def test_preview_editor_preserves_internal_metadata_and_resolves_names(
    client, db_session, importer, existing_student, class_factory
):
    other = class_factory(grade=12, class_name="Other")
    batch = preview(db_session, importer, workbook(db_session, [existing_student]))
    url = f"/admin/import/{batch.token}/rows/2/edit"
    page = client.get(url)
    assert 'name="class_id"' not in page.text
    response = client.post(
        url,
        data={
            "name": existing_student.name,
            "nisn": existing_student.nisn,
            "current": "Aktif",
            "grade": "12",
            "class_name": "Other",
            "revision": "0",
            "class_id": "2147483647",
        },
    )
    assert response.status_code == 200
    db_session.refresh(batch)
    row = next(r for r in batch.payload["rows"] if r["kind"] == "students")
    assert row["values"]["class_id"] == existing_student.class_id
    assert row["resolved_class_id"] == other.class_id
    assert "class_id" in row["changed"]
    apply(db_session, importer, batch)
    db_session.refresh(existing_student)
    assert existing_student.class_id == other.class_id
