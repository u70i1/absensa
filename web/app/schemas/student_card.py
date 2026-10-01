"""Fixed KTP-size cards; only cutting gap and school watermark are editable."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

CARD_WIDTH_MM = Decimal("85.6")
CARD_HEIGHT_MM = Decimal("53.98")


class CardSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gap_mm: Decimal = Field(default=Decimal(3), ge=0, le=200, decimal_places=3)
    school_name: str = Field(default="", max_length=160)
    logo_path: str | None = None

    @property
    def width_mm(self) -> Decimal:
        return CARD_WIDTH_MM

    @property
    def height_mm(self) -> Decimal:
        return CARD_HEIGHT_MM

    @property
    def watermark_enabled(self) -> bool:
        return bool(self.school_name.strip() and self.logo_path)


class CardSettingsUpdate(CardSettings):
    """Editable settings, excluding the fixed card and photo dimensions."""
