from pydantic import BaseModel, Field


class StudentRequest(BaseModel):
    """Request payload schema for POST /student."""
    nisn: str = Field(min_length=10, max_length=10)
    name: str = Field(min_length=1)
    class_id: int | None = None
    current: bool
