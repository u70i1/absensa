from datetime import datetime

from app.db.base import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ScanLog(Base):
    """Records an attendance registration event.

    `name` and `class_name` are stored as snapshots of the student's details
    at the time of the scan and are not updated if the corresponding student
    record changes.

    A student may only be scanned once per day. This constraint is enforced
    at the API layer (see `../routes/scan.py`).
    """

    __tablename__ = "scan_logs"

    scan_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        comment='Foreign key to the "students" table. Set to `NULL` if the '
        "corresponding student is deleted.",
    )

    name: Mapped[str] = mapped_column(
        String(255),
        comment="Student's name at the time of the scan.",
    )

    class_name: Mapped[str] = mapped_column(
        "class",
        String(10),
        nullable=True,
        comment="Student's class at the time of the scan.",
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Time when the scan was recorded, with timezone information.",
    )

    student: Mapped["Student"] = relationship(back_populates="scan_logs")  # pyright: ignore[reportUndefinedVariable]  # noqa: F821

    def __repr__(self):
        return (
            f"ScanLog(id={self.scan_id}, name={self.name}, timestamp={self.timestamp})"
        )
