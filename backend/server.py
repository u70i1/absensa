from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from models.ScanRequest import ScanRequest
from models.ScanResponse import ScanResponse
from utils.scan_modules import get_today_logs, load_students, log_scan

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],    # !change this in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/scan", response_model=ScanResponse)
async def scan(payload: ScanRequest):
    # 1. Load students if cached
    try:
        students = load_students()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 2. Check if student exists
    student = students.get(payload.nisn)
    if student is None:
        raise HTTPException(
            status_code=404, detail={"message": "not_found", "nisn": payload.nisn}
        )

    # 3. Check if already scanned today
    # today_scanned = get_today_logs()
    # if payload.nisn in today_scanned:
    #      raise HTTPException(
    #         status_code=409, detail={"message": "already_exists", "nisn": payload.nisn}
    #     )

    # 4. Log the scan
    log_scan(student)

    # 5. Return success
    return ScanResponse(
        status="success",
        name=student.get("name"),
        class_name=student.get("class"),
        nisn=student.get("nisn"),
        timestamp=datetime.now(tz=timezone.utc).strftime("%H:%M"),
    )


app.mount("/photos", StaticFiles(directory="photos"), name="photos")
