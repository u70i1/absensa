"""Class request, query, and response schemas."""

from app.schemas.base import (
    BulkDeleteRequestBase,
    BulkFailureResponseBase,
    BulkResponseBase,
    BulkSuccessResponseBase,
    OrmResponseBase,
    PaginationQueryBase,
)
from pydantic import BaseModel, Field


class ClassBase(BaseModel):
    """Fields shared by class writes and responses."""

    class_name: str
    grade: int


class ClassWriteRequest(ClassBase):
    """Create or replace a class through POST/PUT /classes."""

    class_name: str = Field(min_length=1, max_length=20)
    grade: int = Field(ge=1, le=20)


class ClassResponse(ClassBase, OrmResponseBase):
    """A stored class returned by class endpoints."""

    class_id: int


class ClassListQuery(PaginationQueryBase):
    """Pagination and filters for GET /classes."""

    class_name: str | None = Field(None, alias="class")


class ClassBulkCreateRequest(BaseModel):
    """One bulk-create item; missing fields are reported by the service per item."""

    class_name: str | None = None
    grade: int | None = None


class ClassBulkUpdateRequest(ClassBulkCreateRequest):
    """One bulk-update item, identified by class_id."""

    class_id: int | None = None


class ClassBulkDeleteRequest(BulkDeleteRequestBase):
    """Class IDs for POST /classes/bulk-delete."""


class ClassBulkFailureItem(BaseModel):
    """Class fields included in a failed bulk result."""

    class_name: str | None


class ClassBulkSuccessResponse(BulkSuccessResponseBase[ClassResponse]):
    """One successfully created or updated class."""


class ClassBulkFailureResponse(BulkFailureResponseBase[ClassBulkFailureItem]):
    """One failed class operation."""


class ClassBulkResponse(
    BulkResponseBase[ClassBulkSuccessResponse, ClassBulkFailureResponse]
):
    """Results of POST/PUT /classes/bulk."""
