from pydantic import BaseModel, ConfigDict


class ScanRequest(BaseModel):
    """Request payload schema for POST /scan."""
    model_config = ConfigDict(coerce_numbers_to_str=True)  # Allows type coercion

    nisn: str
