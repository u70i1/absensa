from app.schemas.StudentResponse import StudentResponse
from pydantic import BaseModel, Field


class FailedStudentItem(BaseModel):
    nisn: str | None = Field(None, min_length=10, max_length=10)
    name: str | None = Field(None, min_length=1)
    class_id: int | None = None
    current: bool | None = True


class StudentSuccess(BaseModel):
    index: int
    student: StudentResponse = Field(description="Represent a successfuly added student." \
    "Use StudentResponse because the structure is the same")


class StudentFailed(BaseModel):
    index: int
    error: str
    student: FailedStudentItem


class BulkStudentResponse(BaseModel):
    """Response schema for POST, PUT /students/bulk"""

    succeeded: list[StudentSuccess]
    failed: list[StudentFailed]
