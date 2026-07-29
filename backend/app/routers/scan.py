from fastapi import APIRouter
from schemas.Scan import ScanRequest, ScanResponse

router = APIRouter()

@router.post("/scan", response_model=ScanResponse)
def scan(payload: ScanRequest):
    # TODO: This route is supposed to receive an NISN number, storing the scan log to its table after processing it.
    pass
