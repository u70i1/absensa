"""Add configurable student card photo ratio, defaulting to 3:4.

Revision ID: f2d918ca64b0
Revises: e8c720a9f431
"""

from alembic import op
import sqlalchemy as sa

revision = "f2d918ca64b0"
down_revision = "e8c720a9f431"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "student_card_settings",
        sa.Column("photo_ratio_width", sa.Double(), nullable=False, server_default="3"),
    )
    op.add_column(
        "student_card_settings",
        sa.Column(
            "photo_ratio_height", sa.Double(), nullable=False, server_default="4"
        ),
    )
    op.create_check_constraint(
        "ck_student_card_photo_ratio",
        "student_card_settings",
        "photo_ratio_width > 0 AND photo_ratio_width < 'Infinity'::float8 "
        "AND photo_ratio_height > 0 AND photo_ratio_height < 'Infinity'::float8",
    )


def downgrade():
    op.drop_constraint(
        "ck_student_card_photo_ratio", "student_card_settings", type_="check"
    )
    op.drop_column("student_card_settings", "photo_ratio_height")
    op.drop_column("student_card_settings", "photo_ratio_width")
