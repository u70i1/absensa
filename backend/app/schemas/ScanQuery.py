from datetime import datetime

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class ScanQuery(BaseModel):
    """Query model for GET /scans"""

    limit: int = Field(30, ge=1, le=100)
    page: int = Field(1, ge=1)
    nisn: str | None = Field(None, min_length=10, max_length=10)
    student_id: int | None = Field(None)
    date_from: datetime | None = Field(None, description="Format: YYYY-MM-DD", examples=["2026-07-10"])
    date_to: datetime | None = Field(None, description="Format: YYYY-MM-DD", examples=["2026-07-10"])

    @model_validator(mode="after")
    def check_date(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_to is earlier than date_from")
        return self
