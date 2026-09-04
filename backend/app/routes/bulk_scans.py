from app.db.session import get_db
from app.schemas.BulkScanRequest import BulkScanIdOnly
from app.services import scan_bulk_service
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/scans/delete-bulk", status_code=204)
def delete_scans_bulk(payload: BulkScanIdOnly, dry_run: bool = False, db: Session = Depends(get_db)):
    missing_ids = scan_bulk_service.delete_scans_bulk(db, payload, dry_run)
    if missing_ids:
        return JSONResponse(
            status_code=422, content=jsonable_encoder({"missing_ids": missing_ids})
        )
