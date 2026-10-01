"""Persist card settings and reuse the validated local photo store for logos."""

from app.models.student_card import StudentCardSettings
from app.schemas.student_card import CardSettings, CardSettingsUpdate
from app.services import student_photo_service as photos
from app.services.exceptions import AppException
from sqlalchemy import select


def get_settings(db) -> CardSettings:
    config = db.get(StudentCardSettings, 1)
    if config is None:
        raise RuntimeError("Student card settings migration has not been applied")
    values = CardSettings.model_validate(config)
    if values.logo_path and not photos.photo_file(values.logo_path).is_file():
        values.logo_path = None
    return values


def update_settings(db, values: CardSettingsUpdate, logo=None, *, remove_logo=False):
    content = photos.normalize_photo(logo) if logo else None
    filename = None
    try:
        config = db.scalar(
            select(StudentCardSettings)
            .where(StudentCardSettings.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if config is None:
            raise RuntimeError("Student card settings migration has not been applied")
        previous = config.logo_path
        school_name = values.school_name.strip()
        retained_logo = previous if not remove_logo else None
        if retained_logo and not photos.photo_file(retained_logo).is_file():
            retained_logo = None
        has_logo = content is not None or bool(retained_logo)
        if bool(school_name) != has_logo:
            raise AppException(
                "Isi nama sekolah dan logo bersama-sama, atau kosongkan keduanya.", 422
            )
        for key, value in values.model_dump(exclude={"logo_path"}).items():
            setattr(config, key, value)
        config.school_name = school_name
        config.watermark_enabled = bool(school_name and has_logo)
        config.logo_path = retained_logo
        if content is not None:
            filename = photos.store_normalized_photo(content)
            config.logo_path = filename
        elif remove_logo:
            config.logo_path = None
        db.commit()
    except Exception:
        db.rollback()
        photos.remove_photo(filename)
        raise
    if filename or remove_logo:
        photos.remove_photo(previous)
    return get_settings(db)
