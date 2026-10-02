"""Shortcut to import all database models. Used by Alembic."""

from app.models.access import Operator, OperatorSession, TrustedDevice  # noqa: F401
from app.models.admin import Admin, AdminSession  # noqa: F401
from app.models.backup import Backup, BackupSettings  # noqa: F401
from app.models.class_ import Class  # noqa: F401
from app.models.import_batch import ImportBatch, ImportPhoto  # noqa: F401
from app.models.login_throttle import LoginThrottle  # noqa: F401
from app.models.scan_log import ScanLog  # noqa: F401
from app.models.student import Student  # noqa: F401
from app.models.student_card import StudentCardSettings  # noqa: F401
from app.models.whatsapp_notification import (  # noqa: F401
    WhatsAppNotificationLog,
    WhatsAppNotificationSettings,
)
