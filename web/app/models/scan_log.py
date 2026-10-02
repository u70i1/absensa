from datetime import datetime
from typing import TYPE_CHECKING

from app.db.base import Base
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.student import Student


class ScanLog(Base):
    """Records an attendance registration event.

    `name` and `class_name` are stored as snapshots of the student's details
    at the time of the scan and are not updated if the corresponding student
    record changes.

    The scan service holds a student row lock while checking and recording the
    current school day, so concurrent requests cannot create duplicate scans.
    """

    __tablename__ = "scan_logs"
    __table_args__ = (
        Index("ix_scan_logs_student_timestamp", "student_id", "timestamp"),
        Index("ix_scan_logs_timestamp_scan_id", "timestamp", "scan_id"),
    )

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
        String(20),
        nullable=True,
        comment="Student's class at the time of the scan.",
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Time when the scan was recorded, with timezone information.",
    )

    student: Mapped["Student | None"] = relationship(back_populates="scan_logs")

    def __repr__(self):
        return (
            f"ScanLog(id={self.scan_id}, name={self.name}, timestamp={self.timestamp})"
        )
