"""Durable backup queue, archive inventory, and school-wide scheduling."""

from datetime import datetime

from app.db.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column


class BackupSettings(Base):
    __tablename__ = "backup_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    times: Mapped[str] = mapped_column(String(11), default="10:00,17:00")
    daily: Mapped[int] = mapped_column(Integer, default=14)
    weekly: Mapped[int] = mapped_column(Integer, default=8)
    monthly: Mapped[int] = mapped_column(Integer, default=3)
    worker_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_backup_settings_singleton"),
        CheckConstraint(
            "daily BETWEEN 1 AND 365 AND weekly BETWEEN 0 AND 104 AND monthly BETWEEN 0 AND 120",
            name="ck_backup_retention",
        ),
    )


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(16))
    slot: Mapped[str | None] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    phase: Mapped[str] = mapped_column(String(24), default="queued")
    size: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None] = mapped_column(String(255))
    retention_error: Mapped[str | None] = mapped_column(String(255))
    integrity_error: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'success', 'failed', 'expired')",
            name="ck_backup_status",
        ),
        CheckConstraint("kind IN ('manual', 'scheduled')", name="ck_backup_kind"),
        Index(
            "uq_backup_active",
            text("(1)"),
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_backup_created_at", "created_at"),
    )
