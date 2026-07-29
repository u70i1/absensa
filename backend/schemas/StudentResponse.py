from pydantic import BaseModel


class StudentResponse(BaseModel):
    """Response schema for individual items of GET /students."""
    id: int
    nisn: str
    name: str
    class_: str
    current: bool
