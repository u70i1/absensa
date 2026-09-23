"""Centralized two-layer browser authentication dependencies."""
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.access import Operator, TrustedDevice
from app.services import access_auth_service as auth

DEVICE_COOKIE = "absensa_trusted_device"
OPERATOR_COOKIE = "absensa_operator"
Db = Annotated[Session, Depends(get_db)]


def safe_destination(value: str | None) -> str:
    # Only the operator application's GET destination is valid after login.
    if not value or any(ord(c) < 32 for c in value) or "\\" in value:
        return "/operator"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "/operator"
    return value if not parsed.scheme and not parsed.netloc and parsed.path == "/operator" and not parsed.fragment else "/operator"


class AccessAuthenticationRequired(Exception):
    def __init__(self, layer: str, destination: str = "/operator"):
        self.layer = layer
        self.location = ("/trusteddevice/login" if layer == "device" else "/operator/login") + "?" + urlencode({"next": safe_destination(destination)})


def get_current_trusted_device(request: Request, db: Db) -> TrustedDevice | None:
    token = request.cookies.get(DEVICE_COOKIE)
    device = auth.device_for_token(db, token)
    if device:
        request.state.renew_device_token = token
    return device


def require_trusted_device(request: Request, device: Annotated[TrustedDevice | None, Depends(get_current_trusted_device)]) -> TrustedDevice:
    if device is None:
        raise AccessAuthenticationRequired("device", str(request.url.path))
    return device


CurrentDevice = Annotated[TrustedDevice, Depends(require_trusted_device)]


def get_current_operator(request: Request, db: Db, device: Annotated[TrustedDevice | None, Depends(get_current_trusted_device)]) -> Operator | None:
    return auth.operator_for_token(db, device, request.cookies.get(OPERATOR_COOKIE))


def require_operator(request: Request, device: CurrentDevice, operator: Annotated[Operator | None, Depends(get_current_operator)]) -> Operator:
    if operator is None:
        raise AccessAuthenticationRequired("operator", str(request.url.path))
    return operator


CurrentOperator = Annotated[Operator, Depends(require_operator)]
