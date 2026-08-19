from app.db.base import Base
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Student(Base):
    """Represent one student or ex-student.

    `ScanLog` references this table via `student_id`, deleting one student
    makes the scan's `student_id` column set to NULL.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("classes.class_id", ondelete="SET NULL"),
        nullable=True,
    )
    nisn: Mapped[str] = mapped_column(
        String(10),
        comment="National student ID number (Indonesia). Always exactly 10 digits. Deferrable. Initially immediate",
    )
    current: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Indicate if a student is still in school or not",
    )
    scan_logs: Mapped[list["ScanLog"]] = relationship(  # pyright: ignore[reportUndefinedVariable]  # noqa: F821
        back_populates="student", order_by="ScanLog.timestamp", passive_deletes=True
    )
    class_: Mapped["Class"] = relationship(back_populates="students")  # pyright: ignore[reportUndefinedVariable]  # noqa: F821

    __table_args__ = (
        UniqueConstraint(
            "nisn", name="students_nisn_key", initially="IMMEDIATE", deferrable=True
        ),
    )

    def __repr__(self):
        return f"Student(id={self.id}, name={self.name}, nisn={self.nisn})"
