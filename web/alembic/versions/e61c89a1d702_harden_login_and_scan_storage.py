"""Add expiring login budgets and allow the full class name in scan snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "e61c89a1d702"
down_revision = "c64e308f7a12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_throttles",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 1", name="ck_login_throttle_attempts"),
    )
    op.create_index("ix_login_throttles_expires_at", "login_throttles", ["expires_at"])
    op.alter_column(
        "scan_logs",
        "class",
        existing_type=sa.String(10),
        type_=sa.String(20),
        existing_nullable=True,
    )
    op.create_index(
        "ix_scan_logs_student_timestamp", "scan_logs", ["student_id", "timestamp"]
    )
    op.create_index(
        "ix_scan_logs_timestamp_scan_id", "scan_logs", ["timestamp", "scan_id"]
    )


def downgrade():
    op.drop_index("ix_scan_logs_timestamp_scan_id", table_name="scan_logs")
    op.drop_index("ix_scan_logs_student_timestamp", table_name="scan_logs")
    # Do not truncate existing 11–20 character snapshots on rollback. PostgreSQL
    # rejects narrowing while such values exist, so operators can retain them.
    op.alter_column(
        "scan_logs",
        "class",
        existing_type=sa.String(20),
        type_=sa.String(10),
        existing_nullable=True,
    )
    op.drop_index("ix_login_throttles_expires_at", table_name="login_throttles")
    op.drop_table("login_throttles")
