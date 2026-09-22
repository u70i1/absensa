"""Validate and store profile photos; paths are relative to PHOTOS_DIR."""

from io import BytesIO
import logging
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4
import warnings

from app.core.config import settings
from app.models.student import Student
from app.services.exceptions import AppException, StudentNotFound
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
logger = logging.getLogger(__name__)


def photo_file(photo_path: str) -> Path:
    root = Path(settings.photos_dir).resolve()
    path = (root / photo_path).resolve()
    if path.parent != root:
        raise AppException("Foto tidak ditemukan.", 404)
    return path


def remove_photo(photo_path: str | None) -> None:
    if photo_path:
        try:
            photo_file(photo_path).unlink(missing_ok=True)
        except (OSError, AppException):
            logger.warning("Could not remove stored student photo", exc_info=True)


def _normalized_photo(source: BinaryIO) -> bytes:
    content = source.read(MAX_PHOTO_BYTES + 1)
    if len(content) > MAX_PHOTO_BYTES:
        raise AppException("Ukuran foto maksimal 5 MB.", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise AppException("Gunakan foto JPEG, PNG, atau WebP.", 415)
                if original.width * original.height > MAX_PHOTO_PIXELS:
                    raise AppException("Resolusi foto maksimal 20 megapiksel.", 413)
                original.load()
                oriented = ImageOps.exif_transpose(original)
                oriented.thumbnail((1024, 1024))
                # Re-encode pixels only: discard metadata and appended content.
                rgba = oriented.convert("RGBA")
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                output = BytesIO()
                clean.save(output, format="JPEG", quality=90)
                return output.getvalue()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise AppException("Resolusi foto terlalu besar.", 413) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise AppException("File foto tidak valid atau rusak.", 415) from exc


def update_student_photo(db: Session, student_id: int, source: BinaryIO) -> str:
    if db.get(Student, student_id) is None:
        raise StudentNotFound(status_code=404)
    content = _normalized_photo(source)
    # Serialize replacements so concurrent uploads clean up the correct old file.
    student = db.scalar(
        select(Student).where(Student.id == student_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if student is None:
        raise StudentNotFound(status_code=404)
    previous_path = student.photo_path
    filename = f"{uuid4().hex}.jpg"
    destination = photo_file(filename)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            output.write(content)
        student.photo_path = filename
        db.commit()
    except Exception:
        db.rollback()
        remove_photo(filename)
        raise
    remove_photo(previous_path)
    return filename


def get_student_photo(db: Session, student_id: int) -> Path:
    student = db.get(Student, student_id)
    if student is None:
        raise StudentNotFound(status_code=404)
    if not student.photo_path:
        raise AppException("Foto tidak ditemukan.", 404)
    path = photo_file(student.photo_path)
    if not path.is_file():
        raise AppException("Foto tidak ditemukan.", 404)
    return path
