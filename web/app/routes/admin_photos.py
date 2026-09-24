"""Administrator-only student photo uploads and downloads."""

from typing import Annotated

from app.core.admin_auth import require_admin
from app.db.session import get_db
from app.schemas.student import StudentPhotoResponse
from app.services import student_photo_service
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin/students", dependencies=[Depends(require_admin)])
Db = Annotated[Session, Depends(get_db)]


@router.post("/{student_id}/photo", response_model=StudentPhotoResponse)
def update_photo(student_id: int, db: Db, photo: Annotated[UploadFile, File()]):
    filename = student_photo_service.update_student_photo(db, student_id, photo.file)
    return StudentPhotoResponse(
        student_id=student_id,
        photo_path=filename,
        photo_url=f"/admin/students/{student_id}/photo?v={filename}",
    )


@router.get("/{student_id}/photo", name="admin_student_photo")
def get_photo(student_id: int, db: Db):
    return FileResponse(
        student_photo_service.get_student_photo(db, student_id),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
