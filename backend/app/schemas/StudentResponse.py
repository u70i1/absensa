from pydantic import BaseModel


class StudentResponse(BaseModel):
    """Response schema for individual items of GET /students."""
    id: int
    nisn: str
    name: str
    class_id: int | None = None
    current: bool
