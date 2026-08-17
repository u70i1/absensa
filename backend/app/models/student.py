from app.db.base import Base
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Student(Base):
    """Represent one student or ex-student.

    One student is optionally registered to a `classes` item via
    `class_id` column; deleting the class will set `class_id`
    to NULL.

    `nisn` column is unique and deferrable.

    `current` column represents if a student is still in school
    or not.

    `ScanLog` references this table via `student_id`.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("classes.class_id", ondelete="SET NULL"), nullable=True
    )
    nisn: Mapped[str] = mapped_column(String(10))
    current: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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
