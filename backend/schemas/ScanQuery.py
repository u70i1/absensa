from datetime import datetime

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class ScanQuery(BaseModel):
    """Query model for GET /scan"""

    limit: int = Field(30, ge=1, le=100)
    page: int = Field(1, ge=1)
    nisn: str | None = Field(None)
    date_from: datetime | None = Field(None)
    date_to: datetime | None = Field(None)

    @model_validator(mode="after")
    def check_date(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_to is earlier than date_from")
        return self
