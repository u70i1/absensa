"""Validated values extracted from the shared spreadsheet templates."""

from app.schemas.class_ import ClassWriteRequest
from app.schemas.student import StudentWriteRequest
from pydantic import Field


class StudentImportRow(StudentWriteRequest):
    id: int | None = Field(None, ge=1, le=2147483647)
    name: str = Field(min_length=1, max_length=255)
    nisn: str = Field(pattern=r"^[0-9]{10}$")
    class_id: int | None = Field(None, ge=1, le=2147483647)


class ClassImportRow(ClassWriteRequest):
    class_id: int | None = Field(None, ge=1, le=2147483647)
