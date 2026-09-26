"""Attendance scan request, query, and response schemas."""

from datetime import date, datetime

from app.schemas.base import BulkDeleteRequestBase, PaginationQueryBase
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self


class ScanCreateRequest(BaseModel):
    """Request payload schema for POST /scans."""

    model_config = ConfigDict(coerce_numbers_to_str=True)  # Allows type coercion

    nisn: str = Field(
        description="National student ID number (Indonesia); always exactly 10 digits"
    )


class ScanListQuery(PaginationQueryBase):
    """Query model for GET /scans"""

    limit: int = Field(30, ge=1, le=100)
    nisn: str | None = Field(None, min_length=10, max_length=10)
    student_id: int | None = None
    date_from: datetime | None = Field(
        None, description="Format: YYYY-MM-DD", examples=["2026-07-10"]
    )
    date_to: datetime | None = Field(
        None, description="Format: YYYY-MM-DD", examples=["2026-07-10"]
    )

    @model_validator(mode="after")
    def check_date(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_to is earlier than date_from")
        return self


class ScanResponse(BaseModel):
    """Response schema for both GET & POST /scans."""

    scan_id: int
    name: str
    class_name: str | None = None
    class_id: int | None = None
    nisn: str | None = Field(
        None,
        description="National student ID number (Indonesia); always exactly 10 digits",
    )
    student_id: int | None = None
    timestamp: datetime


class ScanBulkDeleteRequest(BulkDeleteRequestBase):
    """Scan IDs for POST /scans/delete-bulk."""


class AdminScanQuery(PaginationQueryBase):
    """Single-day filters for the administrator's attendance log."""

    day: date = Field(le=date(9999, 12, 30))
    q: str = Field("", max_length=100)
