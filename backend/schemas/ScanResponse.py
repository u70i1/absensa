from datetime import datetime

from pydantic import BaseModel


class ScanResponse(BaseModel):
    """Response schema for both GET & POST /scan."""
    scan_id: int
    name: str
    class_name: str
    nisn: str
    timestamp: datetime

