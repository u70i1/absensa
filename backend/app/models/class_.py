from app.db.base import Base
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Class(Base):
    """Individual item of "classes" table"""

    __tablename__ = "classes"

    class_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_name: Mapped[str] = mapped_column(String(10), unique=True)

    students: Mapped[list["Student"]] = relationship(back_populates="class_")  # pyright: ignore[reportUndefinedVariable]  # noqa: F821
