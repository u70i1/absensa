from pydantic import BaseModel, Field


class StudentRequest(BaseModel):
    """Request payload schema for POST /student."""

    nisn: str = Field(
        min_length=10,
        max_length=10,
        description="National student ID number (Indonesia); always exactly 10 digits",
    )
    name: str = Field(min_length=1)
    class_id: int | None = None
    current: bool = Field(description="Indicate if a student is graduated or not")
