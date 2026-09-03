from app.schemas.ClassResponse import ClassResponse
from pydantic import BaseModel


class FailedClassItem(BaseModel):
    class_name: str | None


class ClassSuccess(BaseModel):
    index: int
    item: ClassResponse


class ClassFailed(BaseModel):
    index: int
    error: str
    item: FailedClassItem


class BulkClassResponse(BaseModel):
    """Response schema for POST & PUT /classes/bulk"""

    succeeded: list[ClassSuccess]
    failed: list[ClassFailed]
