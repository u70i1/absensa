from pydantic import BaseModel


class BulkScanIdOnly(BaseModel):
    """Request payload schema for POST /scans/delete-bulk"""

    ids: list[int]
