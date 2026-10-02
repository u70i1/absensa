from typing import TYPE_CHECKING

from app.db.base import Base
from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.student import Student


class Class(Base):
    """A school class/section that students belong to.
    Students optionally refer to a class through `class_id`.
    """

    __tablename__ = "classes"

    class_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade: Mapped[int] = mapped_column(Integer)
    class_name: Mapped[str] = mapped_column(
        String(20), comment=("Short, unique name identifying the student group")
    )

    __table_args__ = (
        UniqueConstraint(
            "grade",
            "class_name",
            name="uq_grade_class_name",
            initially="IMMEDIATE",
            deferrable=True,
        ),
    )
    students: Mapped[list["Student"]] = relationship(
        back_populates="class_", passive_deletes=True
    )
