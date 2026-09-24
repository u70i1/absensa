"""Administrator login and logout pages."""

from typing import Annotated

from app.core.admin_auth import ADMIN_SESSION_COOKIE, get_current_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.admin import Admin
from app.schemas.admin import AdminLoginRequest
from app.services import admin_auth_service
from app.templating import templates
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin", default_response_class=HTMLResponse)
Db = Annotated[Session, Depends(get_db)]
OptionalAdmin = Annotated[Admin | None, Depends(get_current_admin)]
LOGIN_ERROR = "Nama pengguna atau kata sandi tidak valid."


def login_page(
    request: Request,
    username: str = "",
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="admin/pages/login.html",
        context={"username": username, "error": error},
        status_code=status_code,
    )


@router.get("", name="admin_login")
def admin_login_page(request: Request, admin: OptionalAdmin):
    if admin is not None:
        return RedirectResponse("/admin/students", status_code=303)
    return login_page(request)


@router.post("", name="admin_login_submit")
async def admin_login(request: Request, db: Db):
    data = dict(await request.form())
    try:
        credentials = AdminLoginRequest.model_validate(data)
    except ValidationError:
        return login_page(request, str(data.get("username", "")), LOGIN_ERROR, 401)

    admin = admin_auth_service.authenticate_admin(
        db, credentials.username, credentials.password
    )
    if admin is None:
        return login_page(request, credentials.username, LOGIN_ERROR, 401)

    token = admin_auth_service.create_admin_session(
        db, admin, settings.admin_session_hours
    )
    response = RedirectResponse("/admin/students", status_code=303)
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/admin")
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        token,
        max_age=settings.admin_session_hours * 60 * 60,
        path="/",
        secure=settings.admin_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/logout", name="admin_logout")
def admin_logout(request: Request, db: Db):
    admin_auth_service.delete_admin_session(
        db, request.cookies.get(ADMIN_SESSION_COOKIE)
    )
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/admin")
    response.delete_cookie(
        ADMIN_SESSION_COOKIE,
        path="/",
        secure=settings.admin_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response
