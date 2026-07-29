from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScanResponse(BaseModel):
    """Response schema for POST /scan."""

    status: Literal["success", "already_scanned"]
    name: str
    class_name: str
    nisn: str
    timestamp: datetime


class ScanRequest(BaseModel):
    """Request payload schema for POST /scan."""

    nisn: str
