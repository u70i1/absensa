"""School-wide WhatsApp settings and the audit trail for daily notifications."""

from datetime import date, datetime, time

from app.db.base import Base
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

DEFAULT_MESSAGE_TEMPLATE = (
    "Yth. orang tua/wali {{nama}}, kami belum mencatat kehadiran "
    "{{nama}} dari kelas {{kelas}} pada hari ini. Mohon konfirmasi kepada sekolah."
)


class WhatsAppNotificationSettings(Base):
    __tablename__ = "whatsapp_notification_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    send_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(9, 0))
    minimum_attendance: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    message_template: Mapped[str] = mapped_column(
        Text, nullable=False, default=DEFAULT_MESSAGE_TEMPLATE
    )
    safe_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_whatsapp_settings_singleton"),
        CheckConstraint(
            "minimum_attendance >= 0", name="ck_whatsapp_minimum_attendance"
        ),
        CheckConstraint("delay_seconds >= 0", name="ck_whatsapp_delay_seconds"),
    )


class WhatsAppNotificationLog(Base):
    """Run, override, test, and per-student delivery events; no message/phone content."""

    __tablename__ = "whatsapp_notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_whatsapp_run_day",
            "day",
            unique=True,
            postgresql_where=text("kind = 'run'"),
        ),
        Index(
            "uq_whatsapp_delivery_day_student",
            "day",
            "student_id",
            unique=True,
            postgresql_where=text("kind = 'delivery' AND student_id IS NOT NULL"),
        ),
        Index("ix_whatsapp_log_day_kind", "day", "kind"),
    )
