from pydantic import BaseModel, Field


class ClassResponse(BaseModel):
    """Response schema for both GET & POST /scan."""
    class_id: int = Field(description='As an id to point to a class in the "class" table')
    class_name: str = Field(description='Represent the class name from the "class" table')

