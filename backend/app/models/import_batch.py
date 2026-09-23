"""Short-lived, administrator-owned import previews and confirmation receipts."""

from datetime import datetime

from app.db.base import Base
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column


class ImportBatch(Base):
    __tablename__ = "import_batches"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ImportPhoto(Base):
    """Validated preview images, discarded on confirmation, cancel, or expiry."""

    __tablename__ = "import_photos"

    batch_token: Mapped[str] = mapped_column(
        ForeignKey("import_batches.token", ondelete="CASCADE"), primary_key=True
    )
    nisn: Mapped[str] = mapped_column(String(10), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
