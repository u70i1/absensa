"""Shortcut to import all database models. Used by Alembic."""

from app.models.access import Operator, OperatorSession, TrustedDevice  # noqa: F401
from app.models.admin import Admin, AdminSession  # noqa: F401
from app.models.class_ import Class  # noqa: F401
from app.models.import_batch import ImportBatch, ImportPhoto  # noqa: F401
from app.models.scan_log import ScanLog  # noqa: F401
from app.models.student import Student  # noqa: F401
