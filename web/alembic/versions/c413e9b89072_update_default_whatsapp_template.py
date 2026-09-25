"""Update the untouched default WhatsApp message template.

Revision ID: c413e9b89072
Revises: 6a8d3f21c490
"""

import sqlalchemy as sa
from alembic import op

revision = "c413e9b89072"
down_revision = "6a8d3f21c490"
branch_labels = None
depends_on = None

OLD_DEFAULT = (
    "Yth. orang tua/wali {{nama}}, kami belum mencatat kehadiran "
    "{{nama}} dari kelas {{kelas}} pada hari ini. Mohon konfirmasi kepada sekolah."
)
NEW_DEFAULT = (
    "Selamat siang Bapak/Ibu Orang Tua/Wali {{nama_siswa}} ({{kelas}}),\n\n"
    "Informasi presensi hari ini menunjukkan {{nama_siswa}} tidak hadir di sekolah.\n\n"
    "_Catatan: Pesan otomatis ini dikirim sebagai konfirmasi harian. "
    "Jika izin/keterangan sudah disampaikan kepada Wali Kelas, "
    "silakan abaikan pesan ini. Terima kasih._"
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE whatsapp_notification_settings SET message_template = :new "
            "WHERE id = 1 AND message_template = :old"
        ),
        {"old": OLD_DEFAULT, "new": NEW_DEFAULT},
    )


def downgrade() -> None:
    # Preserve any message that an administrator may have customized.
    pass
