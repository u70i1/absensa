"""Store administrator-owned import previews.

Revision ID: c82f1a6e940d
Revises: b7e92c41d603
"""

import sqlalchemy as sa
from alembic import op

revision = "c82f1a6e940d"
down_revision = "b7e92c41d603"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "import_batches",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column(
            "admin_id",
            sa.Integer(),
            sa.ForeignKey("admins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_import_batches_admin_id", "import_batches", ["admin_id"])
    op.create_index("ix_import_batches_expires_at", "import_batches", ["expires_at"])


def downgrade():
    op.drop_table("import_batches")
