"""Shortcut to all routes."""

from app.routers.bulk_students import router as bulk_student_router
from app.routers.classes import router as class_router
from app.routers.scan import router as scan_router
from app.routers.students import router as student_router
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(class_router)
api_router.include_router(student_router)
api_router.include_router(scan_router)
api_router.include_router(bulk_student_router)
