from pydantic import BaseModel, Field


class ClassRequest(BaseModel):
    """Request payload schema for POST /classes."""
    class_name: str = Field(min_length=1, max_length=10)
