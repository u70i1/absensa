from app.db.base import Base
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Class(Base):
    """A school class/section that students belong to.

    `Student` references this table via `class_id`; deleting a class
    sets its student's `class_id` ForeignKey to NULL.
    """

    __tablename__ = "classes"

    class_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_name: Mapped[str] = mapped_column(String(10), unique=True)

    students: Mapped[list["Student"]] = relationship(  # noqa: F821 # pyright: ignore[reportUndefinedVariable]
        back_populates="class_", passive_deletes=True
    )
