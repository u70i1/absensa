from app.schemas.ClassResponse import ClassResponse
from pydantic import BaseModel, Field


class FailedClassResponse(BaseModel):
    class_name: str = Field(
        max_length=10, description='Represent the class name from the "class" table'
    )


class ClassSuccess(BaseModel):
    index: int
    class_: ClassResponse = Field()


class ClassFailed(BaseModel):
    index: int
    error: str
    class_: FailedClassResponse


class BulkClassResponse(BaseModel):
    """Response schema for POST & PUT /classes/bulk"""

    succeeded: list[ClassSuccess]
    failed: list[ClassFailed]
