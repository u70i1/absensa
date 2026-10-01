"""Remove card and photo size configuration; preserve gap and school watermark.

Revision ID: c64e308f7a12
Revises: ab47ce918d20
"""

from alembic import op
import sqlalchemy as sa

revision = "c64e308f7a12"
down_revision = "ab47ce918d20"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("ratio", "width", "height", "photo_ratio"):
        op.drop_constraint(
            f"ck_student_card_{name}", "student_card_settings", type_="check"
        )
    for name in ("width_mm", "height_mm", "photo_ratio_width", "photo_ratio_height"):
        op.drop_column("student_card_settings", name)


def downgrade():
    for name, default in (("width_mm", "70"), ("height_mm", "112")):
        op.add_column(
            "student_card_settings",
            sa.Column(name, sa.Numeric(8, 3), nullable=False, server_default=default),
        )
        op.alter_column("student_card_settings", name, server_default=None)
    for name, default in (("photo_ratio_width", "3"), ("photo_ratio_height", "4")):
        op.add_column(
            "student_card_settings",
            sa.Column(name, sa.Double(), nullable=False, server_default=default),
        )
    for name, condition in (
        ("ratio", "width_mm * 8 = height_mm * 5"),
        ("width", "width_mm BETWEEN 40 AND 125"),
        ("height", "height_mm BETWEEN 64 AND 200"),
        (
            "photo_ratio",
            "photo_ratio_width > 0 AND photo_ratio_width < 'Infinity'::float8 AND photo_ratio_height > 0 AND photo_ratio_height < 'Infinity'::float8",
        ),
    ):
        op.create_check_constraint(
            f"ck_student_card_{name}", "student_card_settings", condition
        )
