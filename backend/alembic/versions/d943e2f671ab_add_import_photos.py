"""Stage validated archive photos for import confirmation.

Revision ID: d943e2f671ab
Revises: c82f1a6e940d
"""
from alembic import op
import sqlalchemy as sa

revision = "d943e2f671ab"
down_revision = "c82f1a6e940d"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "import_photos",
        sa.Column("batch_token", sa.String(64), sa.ForeignKey("import_batches.token", ondelete="CASCADE"), primary_key=True),
        sa.Column("nisn", sa.String(10), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
    )


def downgrade():
    op.drop_table("import_photos")
