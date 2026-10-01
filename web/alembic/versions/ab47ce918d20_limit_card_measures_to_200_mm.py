"""Limit card measurements to 200 mm, preserving the 5:8 ratio.

Revision ID: ab47ce918d20
Revises: f2d918ca64b0
"""

from alembic import op

revision = "ab47ce918d20"
down_revision = "f2d918ca64b0"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_student_card_width", "student_card_settings", type_="check")
    op.drop_constraint("ck_student_card_gap", "student_card_settings", type_="check")
    # Existing cards above the new maximum are scaled down without changing ratio.
    op.execute(
        "UPDATE student_card_settings SET width_mm = 125, height_mm = 200 WHERE height_mm > 200"
    )
    op.create_check_constraint(
        "ck_student_card_width", "student_card_settings", "width_mm BETWEEN 40 AND 125"
    )
    op.create_check_constraint(
        "ck_student_card_height",
        "student_card_settings",
        "height_mm BETWEEN 64 AND 200",
    )
    op.create_check_constraint(
        "ck_student_card_gap", "student_card_settings", "gap_mm BETWEEN 0 AND 200"
    )


def downgrade():
    op.drop_constraint("ck_student_card_width", "student_card_settings", type_="check")
    op.drop_constraint("ck_student_card_height", "student_card_settings", type_="check")
    op.drop_constraint("ck_student_card_gap", "student_card_settings", type_="check")
    op.execute("UPDATE student_card_settings SET gap_mm = 20 WHERE gap_mm > 20")
    op.create_check_constraint(
        "ck_student_card_width", "student_card_settings", "width_mm BETWEEN 40 AND 150"
    )
    op.create_check_constraint(
        "ck_student_card_gap", "student_card_settings", "gap_mm BETWEEN 0 AND 20"
    )
