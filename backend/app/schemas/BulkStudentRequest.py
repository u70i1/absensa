from pydantic import BaseModel, Field


class BulkStudentRequest(BaseModel):
    """Single item from request payload schema for POST /student/bulk."""

    nisn: str | None = Field(
        None,
        min_length=10,
        max_length=10,
        description="National student ID number (Indonesia); always exactly 10 digits",
    )
    name: str | None = Field(None, min_length=1)
    class_id: int | None = Field(None)
    current: bool | None = Field(None)


class BulkStudentRequestWithId(BulkStudentRequest):
    """Single item from request payload schema for PUT /students/bulk.

    Extended from BulkStudentRequest by adding id field."""

    id: int | None = Field(None)


class BulkStudentIdOnly(BaseModel):
    """Request payload schema for POST /students/delete-bulk"""

    ids: list[int]
