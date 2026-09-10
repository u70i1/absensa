from pydantic import BaseModel, ConfigDict


class ClassResponse(BaseModel):
    """Response schema for GET & POST /scan."""

    model_config = ConfigDict(from_attributes=True)

    class_id: int
    grade: int
    class_name: str
