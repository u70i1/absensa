"""Student request, query, and response schemas."""

from app.schemas.base import (
    BulkDeleteRequestBase,
    BulkFailureResponseBase,
    BulkResponseBase,
    BulkSuccessResponseBase,
    OrmResponseBase,
    PaginationQueryBase,
)
from pydantic import BaseModel, Field


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


class StudentWriteRequest(StudentBase):
    """Create or replace a student through POST/PUT /students."""


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
