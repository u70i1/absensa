"""Durable backup queue and configuration.

Revision ID: 91e32ac804bf
Revises: e61c89a1d702
"""

from alembic import op
import sqlalchemy as sa

revision = "91e32ac804bf"
down_revision = "e61c89a1d702"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "backup_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("times", sa.String(11), nullable=False),
        sa.Column("daily", sa.Integer(), nullable=False),
        sa.Column("weekly", sa.Integer(), nullable=False),
        sa.Column("monthly", sa.Integer(), nullable=False),
        sa.Column("worker_seen_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("id = 1", name="ck_backup_settings_singleton"),
        sa.CheckConstraint(
            "daily BETWEEN 1 AND 365 AND weekly BETWEEN 0 AND 104 AND monthly BETWEEN 0 AND 120",
            name="ck_backup_retention",
        ),
    )
    op.create_table(
        "backups",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("slot", sa.String(40), unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("size", sa.BigInteger()),
        sa.Column("error", sa.String(255)),
        sa.Column("retention_error", sa.String(255)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'success', 'failed', 'expired')",
            name="ck_backup_status",
        ),
        sa.CheckConstraint("kind IN ('manual', 'scheduled')", name="ck_backup_kind"),
    )
    op.create_index(
        "uq_backup_active",
        "backups",
        [sa.text("(1)")],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index("ix_backup_created_at", "backups", ["created_at"])


def downgrade():
    op.drop_table("backups")
    op.drop_table("backup_settings")
