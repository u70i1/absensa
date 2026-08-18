from pydantic import BaseModel


class ClassResponse(BaseModel):
    """Response schema for GET & POST /scan."""

    class_id: int
    class_name: str
