"""Add database-backed administrator authentication.

Revision ID: a91c7f52e4d8
Revises: 8f2c4a7b1d90
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a91c7f52e4d8"
down_revision: Union[str, Sequence[str], None] = "8f2c4a7b1d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admins_username"), "admins", ["username"], unique=True)
    op.create_table(
        "admin_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(op.f("ix_admin_sessions_admin_id"), "admin_sessions", ["admin_id"])
    op.create_index(
        op.f("ix_admin_sessions_expires_at"), "admin_sessions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_sessions_expires_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_admin_id"), table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_index(op.f("ix_admins_username"), table_name="admins")
    op.drop_table("admins")
