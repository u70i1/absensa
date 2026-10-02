from app.models.scan_log import ScanLog
from app.schemas.scan import ScanBulkDeleteRequest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


def delete_scans_bulk(db: Session, payload: ScanBulkDeleteRequest, dry_run: bool):
    payload_ids = set(payload.ids)
    if not payload_ids:
        return

    db_ids = set(
        db.scalars(select(ScanLog.scan_id).where(ScanLog.scan_id.in_(payload_ids)))
    )
    missing_ids = sorted(payload_ids - db_ids)

    if missing_ids:
        return missing_ids

    if dry_run:
        db.rollback()
    else:
        db.execute(delete(ScanLog).where(ScanLog.scan_id.in_(payload_ids)))
        db.commit()
    return None
