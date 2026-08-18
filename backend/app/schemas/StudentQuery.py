from pydantic import BaseModel, Field


class StudentQuery(BaseModel):
    """Query model for GET /student"""

    limit: int = Field(10, ge=1, le=100)
    page: int = Field(1, ge=1)
    name: str | None = Field(None)
    class_name: str | None = Field(None, alias="class")
    nisn: str | None = Field(
        None,
        description="National student ID number (Indonesia); always exactly 10 digits",
    )
