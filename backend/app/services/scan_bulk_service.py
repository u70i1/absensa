from app.models.scan_log import ScanLog
from app.schemas.BulkScanRequest import BulkScanIdOnly
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


def delete_scans_bulk(db: Session, payload: BulkScanIdOnly, dry_run: bool):
    payload_ids = set(payload.ids)
    if not payload_ids:
        return

    db_ids = set(db.scalars(select(ScanLog.scan_id)).all())

    db_ids = set(db.scalars(select(ScanLog.scan_id)).all())
    missing_ids = [i for i in payload_ids if i not in db_ids]

    if missing_ids:
        return missing_ids

    if dry_run:
        db.rollback()
    else:
        db.execute(delete(ScanLog).where(ScanLog.scan_id.in_(payload_ids)))
    return None
