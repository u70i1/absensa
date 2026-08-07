from datetime import datetime

from pydantic import BaseModel


class ScanResponse(BaseModel):
    """Response schema for both GET & POST /scan."""
    scan_id: int
    name: str
    class_: str
    student_nisn: str
    timestamp: datetime

