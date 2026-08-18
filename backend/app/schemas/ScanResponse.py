from datetime import datetime

from pydantic import BaseModel, Field


class ScanResponse(BaseModel):
    """Response schema for both GET & POST /scan."""

    scan_id: int
    name: str
    class_name: str | None = Field(None)
    class_id: int | None = Field(None)
    nisn: str | None = Field(
        None,
        description="National student ID number (Indonesia); always exactly 10 digits",
    )
    student_id: int | None = Field(None)
    timestamp: datetime
