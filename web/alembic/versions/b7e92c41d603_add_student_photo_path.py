"""Add student profile photo paths.

Revision ID: b7e92c41d603
Revises: a91c7f52e4d8
"""

import sqlalchemy as sa
from alembic import op

revision = "b7e92c41d603"
down_revision = "a91c7f52e4d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("students", sa.Column("photo_path", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("students", "photo_path")
