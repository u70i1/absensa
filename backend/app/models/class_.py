from app.db.base import Base
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Class(Base):
    """Individual item of "class" table"""

    __tablename__ = "class"

    class_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_name: Mapped[str] = mapped_column(String(10))

    students: Mapped[list["Student"]] = relationship(back_populates="class")  # pyright: ignore[reportUndefinedVariable]  # noqa: F821
