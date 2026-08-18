from pydantic import BaseModel, Field


class BulkClassRequest(BaseModel):
    """Single item from request payload schema for POST /classes/bulk."""
    class_name: str = Field(max_length=10)

class BulkClassRequestWithId(BulkClassRequest):
    """Single item from request payload schema for PUT /classes/bulk.

    Extended from BulkClassRequest by adding id field."""
    class_id: int | None = Field(None)

class BulkClassIdOnly(BaseModel):
    """Request payload schema for POST /Classs/delete-bulk"""

    ids: list[int]
