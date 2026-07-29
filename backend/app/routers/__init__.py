"""Shortcut to all routes."""

from app.routers.scan import router as scan_router
from app.routers.student import router as student_router
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(student_router)
api_router.include_router(scan_router)
