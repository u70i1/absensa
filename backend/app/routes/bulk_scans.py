from app.db.session import get_db
from app.models.scan_log import ScanLog
from app.schemas.BulkScanRequest import BulkScanIdOnly
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/scans/delete-bulk", status_code=204)
def delete_students_bulk(payload: BulkScanIdOnly, db: Session = Depends(get_db)):
    payload_ids = set(payload.ids)
    if not payload_ids:
        return

    db_ids = set(db.scalars(select(ScanLog.scan_id)).all())

    missing_ids = []
    for i in payload_ids:
        if i in db_ids:
            continue
        missing_ids.append(i)
    if len(missing_ids) >= 1:
        return JSONResponse(
            status_code=422, content=jsonable_encoder({"missing_ids": missing_ids})
        )

    db.execute(delete(ScanLog).where(ScanLog.scan_id.in_(payload_ids)))
