"""Persist WhatsApp notification settings and event log.

Revision ID: 6a8d3f21c490
Revises: 0fbaf2d5ad9a
"""

from datetime import time

import sqlalchemy as sa
from alembic import op

revision = "6a8d3f21c490"
down_revision = "0fbaf2d5ad9a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_notification_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("send_time", sa.Time(), nullable=False),
        sa.Column("minimum_attendance", sa.Integer(), nullable=False),
        sa.Column("message_template", sa.Text(), nullable=False),
        sa.Column("safe_mode", sa.Boolean(), nullable=False),
        sa.Column("delay_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_whatsapp_settings_singleton"),
        sa.CheckConstraint(
            "minimum_attendance >= 0", name="ck_whatsapp_minimum_attendance"
        ),
        sa.CheckConstraint("delay_seconds >= 0", name="ck_whatsapp_delay_seconds"),
    )
    op.create_table(
        "whatsapp_notification_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_whatsapp_run_day",
        "whatsapp_notification_logs",
        ["day"],
        unique=True,
        postgresql_where=sa.text("kind = 'run'"),
    )
    op.create_index(
        "uq_whatsapp_delivery_day_student",
        "whatsapp_notification_logs",
        ["day", "student_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'delivery' AND student_id IS NOT NULL"),
    )
    op.create_index(
        "ix_whatsapp_log_day_kind", "whatsapp_notification_logs", ["day", "kind"]
    )
    op.bulk_insert(
        sa.table(
            "whatsapp_notification_settings",
            sa.column("id", sa.Integer()),
            sa.column("enabled", sa.Boolean()),
            sa.column("send_time", sa.Time()),
            sa.column("minimum_attendance", sa.Integer()),
            sa.column("message_template", sa.Text()),
            sa.column("safe_mode", sa.Boolean()),
            sa.column("delay_seconds", sa.Integer()),
        ),
        [
            {
                "id": 1,
                "enabled": False,
                "send_time": time(9, 0),
                "minimum_attendance": 20,
                "message_template": (
                    "Yth. orang tua/wali {{nama}}, kami belum mencatat kehadiran "
                    "{{nama}} dari kelas {{kelas}} pada hari ini. Mohon konfirmasi kepada sekolah."
                ),
                "safe_mode": True,
                "delay_seconds": 30,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_log_day_kind", table_name="whatsapp_notification_logs")
    op.drop_index(
        "uq_whatsapp_delivery_day_student", table_name="whatsapp_notification_logs"
    )
    op.drop_index("uq_whatsapp_run_day", table_name="whatsapp_notification_logs")
    op.drop_table("whatsapp_notification_logs")
    op.drop_table("whatsapp_notification_settings")
