from datetime import datetime

from app.db.base import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ScanLog(Base):
    """A log storing one activity of attendance registration.

    One item of `scan_logs` is related to one student via `student_id`;
    deleting the corresponding student sets `student_id` to NULL.

    `name` and `class_name` are not changed alongside corresponding student
    as the log is meant to be a snapshot per scan time.

    One student only gets one scan for one day (enforced from API layer, see
    `../routes/scan.py`).
    """

    __tablename__ = "scan_logs"

    scan_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        comment="Will be set to `NULL` if corresponding student is deleted",
    )
    name: Mapped[str] = mapped_column(String(255))
    class_name: Mapped[str] = mapped_column("class", String(10), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    student: Mapped["Student"] = relationship(back_populates="scan_logs")  # pyright: ignore[reportUndefinedVariable]  # noqa: F821

    def __repr__(self):
        return (
            f"ScanLog(id={self.scan_id}, name={self.name}, timestamp={self.timestamp})"
        )
