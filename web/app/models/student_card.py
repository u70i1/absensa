"""School-wide card configuration, following the existing singleton pattern."""

from decimal import Decimal

from app.db.base import Base
from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class StudentCardSettings(Base):
    __tablename__ = "student_card_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    width_mm: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    height_mm: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    gap_mm: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    school_name: Mapped[str] = mapped_column(String(160), nullable=False)
    logo_path: Mapped[str | None] = mapped_column(String(255))
    watermark_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_student_card_singleton"),
        CheckConstraint("width_mm * 8 = height_mm * 5", name="ck_student_card_ratio"),
        CheckConstraint("width_mm BETWEEN 40 AND 150", name="ck_student_card_width"),
        CheckConstraint("gap_mm BETWEEN 0 AND 20", name="ck_student_card_gap"),
    )
