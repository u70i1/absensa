"""FastAPI dependencies for browser-facing administrator authorization."""

from typing import Annotated

from app.db.session import get_db
from app.models.admin import Admin
from app.services import admin_auth_service
from fastapi import Depends, Request
from sqlalchemy.orm import Session

ADMIN_SESSION_COOKIE = "absensa_admin_session"
AdminDb = Annotated[Session, Depends(get_db)]


class AdminAuthenticationRequired(Exception):
    """Raised when a browser route requires a valid administrator session."""


def get_current_admin(request: Request, db: AdminDb) -> Admin | None:
    return admin_auth_service.admin_for_session(
        db, request.cookies.get(ADMIN_SESSION_COOKIE)
    )


def require_admin(
    admin: Annotated[Admin | None, Depends(get_current_admin)],
) -> Admin:
    if admin is None:
        raise AdminAuthenticationRequired
    return admin


CurrentAdmin = Annotated[Admin, Depends(require_admin)]
