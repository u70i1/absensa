"""Trusted device and operator login/logout using normal browser forms."""

from typing import Annotated
from urllib.parse import urlencode

from app.core.access_auth import (
    DEVICE_COOKIE,
    OPERATOR_COOKIE,
    AccessAuthenticationRequired,
    Db,
    get_current_operator,
    get_current_trusted_device,
    safe_destination,
)
from app.core.browser_security import clear_access_cookies, set_device_cookie
from app.core.config import settings
from app.models.access import Operator, TrustedDevice
from app.services import access_auth_service as auth
from app.services.exceptions import AppException
from app.templating import templates
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

router = APIRouter()
OptionalDevice = Annotated[TrustedDevice | None, Depends(get_current_trusted_device)]
OptionalOperator = Annotated[Operator | None, Depends(get_current_operator)]


def redirect_login(device, operator, destination):
    if operator:
        return RedirectResponse(destination, status_code=303)
    if device:
        return RedirectResponse(
            "/operator/login?" + urlencode({"next": destination}), status_code=303
        )
    return None


def login_response(
    request,
    db,
    layer,
    destination,
    device=None,
    error=None,
    status=200,
    username="",
    operator_id="",
):
    operators = (
        list(
            db.execute(
                select(Operator.id, Operator.display_name)
                .where(Operator.active.is_(True))
                .order_by(Operator.display_name, Operator.id)
            )
        )
        if layer == "operator"
        else []
    )
    locked_until = (
        device.locked_until
        if device and device.locked_until and device.locked_until > auth.now_utc()
        else None
    )
    response = templates.TemplateResponse(
        request=request,
        name="operator/pages/login.html",
        context={
            "layer": layer,
            "destination": destination,
            "error": error,
            "username": username,
            "operator_id": operator_id,
            "operators": operators,
            "device_name": device.username if device else None,
            "locked_until": locked_until,
        },
        status_code=status,
    )
    if locked_until:
        response.headers["Retry-After"] = str(
            max(1, int((locked_until - auth.now_utc()).total_seconds()) + 1)
        )
    clear_access_cookies(response, device=device is None)
    return response


@router.get("/trusteddevice/login", name="trusteddevice_login")
def device_login_page(
    request: Request,
    db: Db,
    device: OptionalDevice,
    operator: OptionalOperator,
    next: str = "/operator",
):
    destination = safe_destination(next)
    return redirect_login(device, operator, destination) or login_response(
        request, db, "device", destination
    )


@router.post("/trusteddevice/login", name="trusteddevice_login_submit")
async def device_login(
    request: Request, db: Db, device: OptionalDevice, operator: OptionalOperator
):
    data = await request.form(max_files=0, max_fields=5)
    destination = safe_destination(str(data.get("next", "")))
    redirect = redirect_login(device, operator, destination)
    if redirect:
        return redirect
    username, password = str(data.get("username", "")), str(data.get("password", ""))
    try:
        if not 1 <= len(username) <= 100 or not 1 <= len(password) <= 1024:
            raise AppException("Nama pengguna atau kata sandi tidak valid.", 401)
        token = await run_in_threadpool(auth.bind_device, db, username, password)
    except AppException as exc:
        db.rollback()
        return login_response(
            request,
            db,
            "device",
            destination,
            error=exc.detail,
            status=exc.status_code,
            username=username[:100],
        )
    response = RedirectResponse(
        "/operator/login?" + urlencode({"next": destination}), status_code=303
    )
    clear_access_cookies(response)
    set_device_cookie(response, token)
    return response


@router.get("/operator/login", name="operator_login")
def operator_login_page(
    request: Request,
    db: Db,
    device: OptionalDevice,
    operator: OptionalOperator,
    next: str = "/operator",
):
    destination = safe_destination(next)
    if not device:
        raise AccessAuthenticationRequired("device", destination)
    if operator:
        return RedirectResponse(destination, status_code=303)
    return login_response(request, db, "operator", destination, device)


@router.post("/operator/login", name="operator_login_submit")
async def operator_login(
    request: Request, db: Db, device: OptionalDevice, operator: OptionalOperator
):
    data = await request.form(max_files=0, max_fields=5)
    destination = safe_destination(str(data.get("next", "")))
    if not device:
        raise AccessAuthenticationRequired("device", destination)
    if operator:
        return RedirectResponse(destination, status_code=303)
    operator_id, pin = str(data.get("operator_id", "")), str(data.get("pin", ""))
    try:
        token = await run_in_threadpool(
            auth.login_operator,
            db,
            request.cookies.get(DEVICE_COOKIE),
            operator_id,
            pin,
        )
    except AppException as exc:
        db.rollback()
        device = auth.device_for_token(db, request.cookies.get(DEVICE_COOKIE))
        if device is None:
            raise AccessAuthenticationRequired("device", destination)
        return login_response(
            request,
            db,
            "operator",
            destination,
            device,
            exc.detail,
            exc.status_code,
            operator_id=operator_id[:10],
        )
    response = RedirectResponse(destination, status_code=303)
    response.set_cookie(
        OPERATOR_COOKIE,
        token,
        path="/",
        secure=settings.access_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/operator/logout", name="operator_logout")
def operator_logout(request: Request, db: Db):
    auth.logout_operator(
        db, request.cookies.get(DEVICE_COOKIE), request.cookies.get(OPERATOR_COOKIE)
    )
    response = RedirectResponse("/operator/login", status_code=303)
    clear_access_cookies(response)
    return response


@router.post("/trusteddevice/logout", name="trusteddevice_logout")
def device_logout(request: Request, db: Db):
    auth.logout_device(db, request.cookies.get(DEVICE_COOKIE))
    request.state.clear_device_cookie = True
    response = RedirectResponse("/trusteddevice/login", status_code=303)
    clear_access_cookies(response, device=True)
    return response
