from app.schemas.BulkStudentRequest import BulkStudentRequest
from app.schemas.StudentResponse import StudentResponse
from pydantic import BaseModel


class StudentWithId(StudentResponse):
    id: int | None = None


class StudentSuccess(BaseModel):
    index: int
    student: StudentWithId


class StudentFailed(BaseModel):
    index: int
    error: str
    student: BulkStudentRequest


class BulkStudentResponse(BaseModel):
    """Response schema for POST /students/bulk."""

    succeeded: list[StudentSuccess]
    failed: list[StudentFailed]
