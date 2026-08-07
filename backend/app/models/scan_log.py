from datetime import datetime

from app.db.base import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ScanLog(Base):
    """Individual item of "scan_logs" table"""

    __tablename__ = "scan_logs"

    scan_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_nisn: Mapped[str] = mapped_column(ForeignKey("students.nisn", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    class_: Mapped[str] = mapped_column("class", String(10))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="scan_logs")  # pyright: ignore[reportUndefinedVariable]  # noqa: F821

    def __repr__(self):
        return (
            f"ScanLog(id={self.scan_id}, name={self.name}, timestamp={self.timestamp})"
        )
