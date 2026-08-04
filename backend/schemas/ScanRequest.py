from pydantic import BaseModel


class ScanRequest(BaseModel):
    """Request payload schema for POST /scan."""
    nisn: str
