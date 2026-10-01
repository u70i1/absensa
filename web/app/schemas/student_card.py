"""Physical card values; dimensions are validated together on every save."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CardSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    width_mm: Decimal = Field(default=Decimal(70), ge=40, le=125, decimal_places=3)
    height_mm: Decimal = Field(default=Decimal(112), ge=64, le=200, decimal_places=3)
    gap_mm: Decimal = Field(default=Decimal(3), ge=0, le=200, decimal_places=3)
    photo_ratio_width: float = Field(default=3.0, gt=0, allow_inf_nan=False)
    photo_ratio_height: float = Field(default=4.0, gt=0, allow_inf_nan=False)
    school_name: str = Field(default="", max_length=160)
    logo_path: str | None = None

    @property
    def watermark_enabled(self) -> bool:
        return bool(self.school_name.strip() and self.logo_path)

    @model_validator(mode="after")
    def fixed_ratio(self):
        if self.width_mm * 8 != self.height_mm * 5:
            raise ValueError("Ukuran kartu harus memiliki rasio 5:8.")
        return self


class CardSettingsUpdate(CardSettings):
    dimension_source: Literal["width", "height"] = "width"

    @model_validator(mode="before")
    @classmethod
    def synchronize_dimensions(cls, values):
        values = dict(values)
        source = values.get("dimension_source", "width")
        if source == "width":
            values["height_mm"] = Decimal(str(values.get("width_mm", 70))) * 8 / 5
        elif source == "height":
            values["width_mm"] = Decimal(str(values.get("height_mm", 112))) * 5 / 8
        return values
