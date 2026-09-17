"""Add guardian phone number to students.

Revision ID: 8f2c4a7b1d90
Revises: 53e0df381460
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f2c4a7b1d90"
down_revision: Union[str, Sequence[str], None] = "53e0df381460"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column(
            "guardian_phone",
            sa.String(length=32),
            nullable=True,
            comment="Phone number of the student's guardian.",
        ),
    )


def downgrade() -> None:
    op.drop_column("students", "guardian_phone")
