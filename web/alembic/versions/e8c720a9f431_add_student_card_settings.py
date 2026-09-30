"""Add global student card settings.

Revision ID: e8c720a9f431
Revises: c413e9b89072
"""

from alembic import op
import sqlalchemy as sa

revision = "e8c720a9f431"
down_revision = "c413e9b89072"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "student_card_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("width_mm", sa.Numeric(8, 3), nullable=False),
        sa.Column("height_mm", sa.Numeric(8, 3), nullable=False),
        sa.Column("gap_mm", sa.Numeric(6, 3), nullable=False),
        sa.Column("school_name", sa.String(160), nullable=False),
        sa.Column("logo_path", sa.String(255)),
        sa.Column("watermark_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_student_card_singleton"),
        sa.CheckConstraint(
            "width_mm * 8 = height_mm * 5", name="ck_student_card_ratio"
        ),
        sa.CheckConstraint("width_mm BETWEEN 40 AND 150", name="ck_student_card_width"),
        sa.CheckConstraint("gap_mm BETWEEN 0 AND 20", name="ck_student_card_gap"),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": 1,
                "width_mm": 70,
                "height_mm": 112,
                "gap_mm": 3,
                "school_name": "",
                "watermark_enabled": False,
            }
        ],
    )


def downgrade():
    op.drop_table("student_card_settings")
