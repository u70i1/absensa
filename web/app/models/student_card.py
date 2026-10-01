"""School-wide card configuration, following the existing singleton pattern."""

from decimal import Decimal

from app.db.base import Base
from sqlalchemy import Boolean, CheckConstraint, Double, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class StudentCardSettings(Base):
    __tablename__ = "student_card_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    width_mm: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    height_mm: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    gap_mm: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    photo_ratio_width: Mapped[float] = mapped_column(
        Double, nullable=False, server_default="3"
    )
    photo_ratio_height: Mapped[float] = mapped_column(
        Double, nullable=False, server_default="4"
    )
    school_name: Mapped[str] = mapped_column(String(160), nullable=False)
    logo_path: Mapped[str | None] = mapped_column(String(255))
    watermark_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_student_card_singleton"),
        CheckConstraint("width_mm * 8 = height_mm * 5", name="ck_student_card_ratio"),
        CheckConstraint("width_mm BETWEEN 40 AND 125", name="ck_student_card_width"),
        CheckConstraint("height_mm BETWEEN 64 AND 200", name="ck_student_card_height"),
        CheckConstraint("gap_mm BETWEEN 0 AND 200", name="ck_student_card_gap"),
        CheckConstraint(
            "photo_ratio_width > 0 AND photo_ratio_width < 'Infinity'::float8 "
            "AND photo_ratio_height > 0 AND photo_ratio_height < 'Infinity'::float8",
            name="ck_student_card_photo_ratio",
        ),
    )
