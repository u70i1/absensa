from pydantic import BaseModel, ConfigDict, Field


class ScanRequest(BaseModel):
    """Request payload schema for POST /scan."""

    model_config = ConfigDict(coerce_numbers_to_str=True)  # Allows type coercion

    nisn: str = Field(
        description="National student ID number (Indonesia); always exactly 10 digits"
    )
