from pydantic import BaseModel, Field


class BulkStudentRequest(BaseModel):
    """Single item from request payload schema for POST /student/bulk."""
    nisn: str | None = Field(None, min_length=10, max_length=10)
    name: str | None = Field(None, min_length=1)
    class_id: int | None = None
    current: bool | None
