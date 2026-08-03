from datetime import datetime

from pydantic import BaseModel


class ScanResponse(BaseModel):
    """Response schema for POST /scan."""
    name: str
    class_name: str
    nisn: str
    timestamp: datetime


class ScanRequest(BaseModel):
    """Request payload schema for POST /scan."""

    nisn: str
