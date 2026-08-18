from pydantic import BaseModel, Field


class ClassQuery(BaseModel):
    """Query model for GET /classes"""

    limit: int = Field(10, ge=1, le=100)
    page: int = Field(1, ge=1)
    class_name: str | None = Field(None, alias="class")
