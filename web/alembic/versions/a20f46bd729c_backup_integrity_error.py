"""Persist failed backup integrity checks.

Revision ID: a20f46bd729c
Revises: 91e32ac804bf
"""

from alembic import op
import sqlalchemy as sa

revision = "a20f46bd729c"
down_revision = "91e32ac804bf"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("backups", sa.Column("integrity_error", sa.String(255)))


def downgrade():
    op.drop_column("backups", "integrity_error")
