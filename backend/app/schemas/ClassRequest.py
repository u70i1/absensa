from pydantic import BaseModel, Field


class ClassRequest(BaseModel):
    """Request payload schema for POST /classes."""

    class_name: str = Field(min_length=1, max_length=20)
    grade: int = Field(ge=1, le=20)
