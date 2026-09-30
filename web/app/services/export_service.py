"""Build spreadsheet exports from the versioned workbook templates."""

from copy import copy
from datetime import datetime
from io import BytesIO
from pathlib import Path
from secrets import token_urlsafe
from zoneinfo import ZoneInfo

from app.core.config import settings
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Protection
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.workbook.properties import CalcProperties
from openpyxl.worksheet.datavalidation import DataValidation

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "spreadsheet_templates"
STUDENT_TEMPLATE = TEMPLATE_DIR / "students_export_template.xlsx"
STUDENT_COLUMNS = (
    ("ID", "id"),
    ("NAMA", "name"),
    ("NISN", "nisn"),
    ("STATUS", "current"),
    ("NOMOR WALI", "guardian_phone"),
    ("JENJANG", "grade"),
    ("NAMA KELAS", "class_name"),
    ("ID KELAS", "class_id"),
)
CLASS_COLUMNS = (
    ("ID KELAS", "class_id"),
    ("JENJANG", "grade"),
    ("NAMA KELAS", "class_name"),
)
SCAN_TEMPLATE = TEMPLATE_DIR / "scans_export_template.xlsx"
SCAN_HEADERS = ("ID LOG", "NAMA SISWA", "KELAS", "NISN", "TANGGAL", "WAKTU")
NEW_ENTRY_ROWS = 100


def _copy_cell_style(source, target) -> None:
    target._style = copy(source._style)
    target.number_format = source.number_format
    target.protection = copy(source.protection)
    target.alignment = copy(source.alignment)


def _prepare_new_rows(sheet, column_count: int, last_data_row: int) -> None:
    """Keep a styled entry area after exports, including text-only identifiers.

    Validation and column number formats also cover rows beyond this area in
    the source templates, without materializing a million empty cells.
    """
    last_entry_row = min(1048576, last_data_row + NEW_ENTRY_ROWS)
    for row_number in range(last_data_row + 1, last_entry_row + 1):
        sheet.row_dimensions[row_number].height = sheet.row_dimensions[2].height
        for column in range(1, column_count + 1):
            _copy_cell_style(sheet.cell(2, column), sheet.cell(row_number, column))


def _replace_metadata(workbook, replacements: dict[str, object]) -> None:
    sheet = workbook[
        "instructions" if "instructions" in workbook.sheetnames else "Tentang Ekspor"
    ]
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value in replacements:
                cell.value = replacements[cell.value]


def _populate_sheet(sheet, columns, items):
    if tuple(
        sheet.cell(1, column).value for column in range(1, len(columns) + 1)
    ) != tuple(header for header, _ in columns):
        raise ValueError(
            f"Columns in {sheet.title} template do not match the configured mapping."
        )
    for number, item in enumerate(items, 2):
        sheet.row_dimensions[number].height = sheet.row_dimensions[2].height
        for column, (_, field) in enumerate(columns, 1):
            cell = sheet.cell(number, column)
            _copy_cell_style(sheet.cell(2, column), cell)
            value = getattr(item, field, None)
            cell.value = (
                ("Aktif" if value else "Tidak aktif") if field == "current" else value
            )
            if isinstance(cell.value, str):
                cell.data_type = "s"
    last = max(2, len(items) + 1)
    table = next(iter(sheet.tables.values()))
    table.ref = f"A1:{get_column_letter(len(columns))}{last}"
    table.autoFilter.ref = table.ref
    _prepare_new_rows(sheet, len(columns), last)


def _dropdown(sheet, cells, formula, *, strict=True):
    validation = DataValidation(type="list", formula1=formula, allow_blank=True)
    validation.showErrorMessage = strict
    validation.errorTitle = "Pilihan tidak valid"
    validation.error = "Pilih nilai yang tersedia pada sheet classes."
    validation.showDropDown = False
    sheet.add_data_validation(validation)
    validation.add(cells)


def _protect_data_sheet(sheet, editable_columns):
    """Protect identities/helpers while keeping data fields and new entry rows editable."""
    for column in editable_columns:
        sheet.column_dimensions[get_column_letter(column)].protection = Protection(
            locked=False
        )
    for row in sheet.iter_rows():
        for cell in row:
            cell.protection = Protection(
                locked=cell.row == 1 or cell.column not in editable_columns
            )
    sheet.protection.sheet = True
    sheet.protection.set_password(token_urlsafe(16))
    sheet.protection.autoFilter = False
    sheet.protection.insertRows = False
    sheet.protection.deleteRows = False
    sheet.protection.selectLockedCells = True
    sheet.protection.selectUnlockedCells = False


def build_students_workbook(students, filter_summary: str, classes) -> bytes:
    """Build the editable combined workbook using the existing Absensa styles.

    Callers must supply the complete class directory, independently of filters.
    """
    workbook = load_workbook(STUDENT_TEMPLATE)
    students, classes = list(students), list(classes)
    _replace_metadata(
        workbook,
        {
            "{{ filter_summary }}": filter_summary,
            "{{ exported_at }}": datetime.now(ZoneInfo(settings.timezone)).strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            ),
            "{{ row_count }}": len(students),
        },
    )
    sheet, class_sheet = workbook["students"], workbook["classes"]
    _populate_sheet(sheet, STUDENT_COLUMNS, students)
    _populate_sheet(class_sheet, CLASS_COLUMNS, classes)
    # Visible values always come from the actual FK, never denormalized row text.
    by_id = {item.class_id: item for item in classes}
    for number, student in enumerate(students, 2):
        assigned = by_id.get(student.class_id)
        sheet.cell(number, 6).value = assigned.grade if assigned else None
        cell = sheet.cell(number, 7)
        cell.value = assigned.class_name if assigned else None
        if isinstance(cell.value, str):
            cell.data_type = "s"
    # Retain existing validation for non-class student fields.
    sheet.data_validations.dataValidation = [
        dv for dv in sheet.data_validations.dataValidation if "H2" not in dv.sqref
    ]
    for dv in sheet.data_validations.dataValidation:
        if "D2" in dv.sqref:
            dv.formula1 = '"Aktif,Tidak aktif"'
    class_sheet.data_validations.dataValidation = [
        dv for dv in class_sheet.data_validations.dataValidation if "B2" not in dv.sqref
    ]
    grades = sorted({item.grade for item in classes})
    for row, grade in enumerate(grades, 2):
        class_sheet.cell(row, 5, grade)
    class_sheet.column_dimensions["E"].hidden = True
    workbook.defined_names.add(
        DefinedName(
            "jenjang_list", attr_text=f"'classes'!$E$2:$E${max(2, len(grades) + 1)}"
        )
    )
    for column, grade in enumerate(grades, 6):
        letter = get_column_letter(column)
        names = [item.class_name for item in classes if item.grade == grade]
        for row, name in enumerate(names, 2):
            cell = class_sheet.cell(row, column, name)
            cell.data_type = "s"
        class_sheet.column_dimensions[letter].hidden = True
        workbook.defined_names.add(
            DefinedName(
                f"kelas_{grade}",
                attr_text=f"'classes'!${letter}$2:${letter}${len(names) + 1}",
            )
        )
    _dropdown(sheet, "F2:F1048576", "jenjang_list", strict=False)
    _dropdown(sheet, "G2:G1048576", 'INDIRECT("kelas_"&$F2)', strict=False)
    _dropdown(class_sheet, "B2:B1048576", "jenjang_list", strict=False)
    _protect_data_sheet(sheet, editable_columns=range(2, 8))
    _protect_data_sheet(class_sheet, editable_columns=range(2, 4))
    sheet.column_dimensions["H"].hidden = True
    sheet["H1"].comment = Comment(
        "Metadata internal Absensa. Jangan mengubah ID kelas siswa; pilih jenjang dan nama kelas.",
        "Absensa",
    )
    for target in (sheet, class_sheet):
        target.cell(1, 1).comment = Comment(
            "ID dilindungi dan tidak boleh diubah. Baris baru menggunakan ID kosong.",
            "Absensa",
        )
    workbook.calculation = CalcProperties(
        calcMode="auto", fullCalcOnLoad=True, forceFullCalc=True
    )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_scans_workbook(scans, filter_summary: str) -> bytes:
    """Export attendance history in the same visual style, without import rows."""
    workbook = load_workbook(SCAN_TEMPLATE)
    sheet = workbook["scan_logs"]
    actual_headers = tuple(sheet.cell(1, column).value for column in range(1, 7))
    if actual_headers != SCAN_HEADERS:
        raise ValueError(
            "Scan export template columns do not match the configured mapping: "
            f"expected {SCAN_HEADERS}, found {actual_headers}."
        )
    scans = list(scans)
    exported_at = datetime.now(ZoneInfo(settings.timezone))
    _replace_metadata(
        workbook,
        {
            "{{ filter_summary }}": filter_summary,
            "{{ exported_at }}": exported_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "{{ row_count }}": len(scans),
        },
    )
    style_cells = tuple(sheet.cell(2, column) for column in range(1, 7))
    local_timezone = ZoneInfo(settings.timezone)
    for row_number, scan in enumerate(scans, start=2):
        if row_number > 2:
            sheet.row_dimensions[row_number].height = sheet.row_dimensions[2].height
        local_time = scan.timestamp.astimezone(local_timezone)
        values = (
            scan.scan_id,
            scan.name,
            scan.class_name,
            scan.nisn,
            local_time.date(),
            local_time.time().replace(tzinfo=None),
        )
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row_number, column)
            _copy_cell_style(style_cells[column - 1], cell)
            cell.value = value
            if isinstance(value, str):
                cell.data_type = "s"
    last_row = max(2, len(scans) + 1)
    table = sheet.tables["ScansExportTable"]
    table.ref = f"A1:F{last_row}"
    if table.autoFilter is not None:
        table.autoFilter.ref = table.ref
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
