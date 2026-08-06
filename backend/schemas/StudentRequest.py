from pydantic import BaseModel, Field


class StudentRequest(BaseModel):
    """Request payload schema for POST /student."""
    nisn: str = Field(min_length=10, max_length=10)
    name: str = Field(min_length=1)
    class_: str = Field(max_length=10)
    current: bool | None = True
