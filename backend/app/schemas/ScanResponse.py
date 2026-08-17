from datetime import datetime

from pydantic import BaseModel


class ScanResponse(BaseModel):
    """Response schema for both GET & POST /scan."""

    scan_id: int
    name: str
    class_name: str | None = None
    class_id: int | None = None
    nisn: str | None = None
    student_id: int | None = None
    timestamp: datetime
