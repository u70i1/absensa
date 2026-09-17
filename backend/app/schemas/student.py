"""Student request, query, and response schemas."""

from app.schemas.base import (
    BulkDeleteRequestBase,
    BulkFailureResponseBase,
    BulkResponseBase,
    BulkSuccessResponseBase,
    OrmResponseBase,
    PaginationQueryBase,
)
from pydantic import BaseModel, Field, field_validator


def normalize_guardian_phone(value: object) -> str | None:
    """Accept an optional Indonesian guardian phone number in digits-only form."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError("Nomor wali hanya boleh berisi angka.")
    if not value.startswith(("628", "08")):
        raise ValueError("Nomor wali harus diawali 628 atau 08.")
    return value


class StudentBase(BaseModel):
    """Student fields shared by write requests and responses."""

    nisn: str = Field(
        min_length=10,
        max_length=10,
        description="National student ID number (Indonesia); always exactly 10 digits",
    )
    name: str = Field(min_length=1)
    class_id: int | None = None
    current: bool = Field(description="Indicate if a student is graduated or not")
    guardian_phone: str | None = Field(
        default=None, max_length=32, description="Phone number of the student's guardian."
    )

    def model_dump(self, *args, **kwargs):
        values = super().model_dump(*args, **kwargs)
        if self.guardian_phone is None and "guardian_phone" not in self.model_fields_set:
            values.pop("guardian_phone", None)
        return values


class StudentWriteRequest(StudentBase):
    """Create or replace a student through POST/PUT /students."""

    @field_validator("guardian_phone", mode="before")
    @classmethod
    def validate_guardian_phone(cls, value: object) -> str | None:
        return normalize_guardian_phone(value)


class StudentResponse(StudentBase, OrmResponseBase):
    """A stored student returned by student endpoints."""

    id: int
    class_name: str | None = None


class ClassStudentListQuery(PaginationQueryBase):
    """Pagination and filters for GET /classes/{class_id}/students."""

    name: str | None = None
    nisn: str | None = Field(
        None,
        description="National student ID number (Indonesia); always exactly 10 digits",
    )


class StudentListQuery(ClassStudentListQuery):
    """Pagination and filters for GET /students, including class name."""

    class_name: str | None = Field(None, alias="class")
    grade: int | None = None
    class_id: int | None = None
    unassigned: bool = False
    q: str | None = Field(None, description="Search by name substring or exact NISN.")


class StudentBulkCreateRequest(BaseModel):
    """One bulk-create item; missing fields are reported by the service per item."""

    nisn: str | None = Field(
        None,
        min_length=10,
        max_length=10,
        description="National student ID number (Indonesia); always exactly 10 digits",
    )
    name: str | None = Field(None, min_length=1)
    class_id: int | None = None
    current: bool | None = None
    guardian_phone: str | None = Field(default=None, max_length=32)

    def model_dump(self, *args, **kwargs):
        values = super().model_dump(*args, **kwargs)
        if self.guardian_phone is None and "guardian_phone" not in self.model_fields_set:
            values.pop("guardian_phone", None)
        return values

    @field_validator("guardian_phone", mode="before")
    @classmethod
    def validate_guardian_phone(cls, value: object) -> str | None:
        return normalize_guardian_phone(value)


class StudentBulkUpdateRequest(StudentBulkCreateRequest):
    """One bulk-update item, identified by id."""

    id: int | None = None


class StudentBulkDeleteRequest(BulkDeleteRequestBase):
    """Student IDs for POST /students/bulk-delete."""


class StudentBulkFailureItem(StudentBulkCreateRequest):
    """Student fields included in a failed bulk result."""

    current: bool | None = True


class StudentBulkSuccessResponse(BulkSuccessResponseBase[StudentResponse]):
    """One successfully created or updated student."""


class StudentBulkFailureResponse(BulkFailureResponseBase[StudentBulkFailureItem]):
    """One failed student operation."""


class StudentBulkResponse(
    BulkResponseBase[StudentBulkSuccessResponse, StudentBulkFailureResponse]
):
    """Results of POST/PUT /students/bulk."""

    def model_dump(self, *args, **kwargs):
        values = super().model_dump(*args, **kwargs)
        for branch in ("succeeded", "failed"):
            for result in values.get(branch, []):
                item = result.get("item", {})
                if item.get("guardian_phone") is None:
                    item.pop("guardian_phone", None)
        return values
