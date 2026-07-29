"""
Legacy code. Might not work anymore.
"""

from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from models.ScanRequest import ScanRequest
from backend.models.StudentResponse import ScanResponse
from sqlalchemy import Integer, String, create_engine, select
from sqlalchemy.orm import (
    Mapped,
    Session,
    declarative_base,
    mapped_column,
    sessionmaker,
)
from utils.scan_modules import get_today_logs, load_students, log_scan

load_dotenv()


app = FastAPI(title="praesens API")



# Database setup
engine = create_engine(DATABASE_URL)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.post("/scan", response_model=ScanResponse)
async def scan(payload: ScanRequest):
    # 1. Load students if cached

    # 2. Check if student exists

    # 3. Check if already scanned today

    # 4. Log the scan
    pass


app.mount("/photos", StaticFiles(directory="photos"), name="photos")
