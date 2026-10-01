"""Validated values extracted from the shared spreadsheet templates."""

from typing import Annotated

from app.schemas.class_ import ClassWriteRequest
from app.schemas.student import StudentWriteRequest
from pydantic import Field

ClassReference = (
    Annotated[int, Field(ge=1, le=2147483647)]
    | Annotated[str, Field(pattern=r"^N[1-9][0-9]*$", max_length=12)]
)


class StudentImportRow(StudentWriteRequest):
    id: int | None = Field(None, ge=1, le=2147483647)
    name: str = Field(min_length=1, max_length=255)
    nisn: str = Field(pattern=r"^[0-9]{10}$")
    class_id: ClassReference | None = None

    grade: int | None = Field(None, ge=1, le=20)
    class_name: str | None = Field(None, min_length=1, max_length=20)


class ClassImportRow(ClassWriteRequest):
    class_id: ClassReference | None = None
