from app.db.base import Base
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Class(Base):
    """A school class/section that students belong to.
    Students optionally refer to a class through `class_id`.
    """

    __tablename__ = "classes"

    class_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_name: Mapped[str] = mapped_column(
        String(10), unique=True, comment=("Short, unique name identifying the student group")
    )

    students: Mapped[list["Student"]] = relationship(  # noqa: F821 # pyright: ignore[reportUndefinedVariable]
        back_populates="class_", passive_deletes=True
    )
