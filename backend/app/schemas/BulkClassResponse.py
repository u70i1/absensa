from app.schemas.ClassResponse import ClassResponse
from pydantic import BaseModel, Field


class FailedClassItem(BaseModel):
    class_name: str | None = Field(
        "", description='Represent the class name from the "class" table'
    )


class ClassSuccess(BaseModel):
    index: int
    class_: ClassResponse = Field(alias="class")


class ClassFailed(BaseModel):
    index: int
    error: str
    class_: FailedClassItem = Field(alias="class")


class BulkClassResponse(BaseModel):
    """Response schema for POST & PUT /classes/bulk"""

    succeeded: list[ClassSuccess]
    failed: list[ClassFailed]
