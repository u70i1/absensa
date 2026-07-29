from app.db.base import Base
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    class_: Mapped[str] = mapped_column("class", String, nullable=False)
    nisn: Mapped[str] = mapped_column(String(10), unique=True)
    current: Mapped[bool] = mapped_column(
        Boolean, default=True
    )  # Whether they've graduated or not

    scan_logs: Mapped[list["ScanLog"]] = relationship(  # pyright: ignore[reportUndefinedVariable]  # noqa: F821
        back_populates="student", order_by="ScanLog.timestamp"
    )

    def __repr__(self):
        return f"Student(id={self.id}, name={self.name}, nisn={self.nisn})"
