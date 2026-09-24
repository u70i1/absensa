"""Opaque sessions, persistent single-device binding, and serialized PIN attempts."""

import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from app.models.access import Operator, OperatorSession, TrustedDevice
from app.services.admin_auth_service import (
    hash_password,
    normalize_username,
    password_hasher,
)
from app.services.exceptions import AppException
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

_DUMMY_HASH = hash_password(token_urlsafe(32))
MAX_PIN_FAILURES = 5
PIN_LOCKOUT = timedelta(minutes=5)


def now_utc():
    return datetime.now(timezone.utc)


def token_digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def verify_secret(encoded: str | None, secret: str) -> bool:
    try:
        return password_hasher.verify(encoded or _DUMMY_HASH, secret)
    except (VerificationError, InvalidHashError):
        return False


def device_for_token(db: Session, token: str | None, *, lock=False):
    if not token or len(token) > 256:
        return None
    stmt = select(TrustedDevice).where(
        TrustedDevice.binding_hash == token_digest(token),
        TrustedDevice.active.is_(True),
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def bind_device(db: Session, username: str, password: str) -> str:
    device = db.scalar(
        select(TrustedDevice)
        .where(TrustedDevice.username == normalize_username(username))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    valid = verify_secret(device.password_hash if device else None, password)
    if not valid or device is None or not device.active:
        raise AppException("Nama pengguna atau kata sandi tidak valid.", 401)
    if device.binding_hash:
        raise AppException(
            "Akun perangkat sudah terhubung. Minta admin mereset koneksi perangkat sebelum masuk kembali.",
            409,
        )
    token = token_urlsafe(32)
    device.binding_hash = token_digest(token)
    device.bound_at = now_utc()
    if password_hasher.check_needs_rehash(device.password_hash):
        device.password_hash = hash_password(password)
    db.commit()
    return token


def revoke_binding(db: Session, device: TrustedDevice, *, reset_lock=True):
    """Caller holds the device row lock and commits the surrounding transaction."""
    db.execute(delete(OperatorSession).where(OperatorSession.device_id == device.id))
    device.binding_hash = None
    device.bound_at = None
    if reset_lock:
        device.pin_failures = 0
        device.locked_until = None


def logout_device(db: Session, token: str | None):
    device = device_for_token(db, token, lock=True)
    if device:
        # A device user must not evade PIN throttling by logging out/rebinding.
        revoke_binding(db, device, reset_lock=False)
    db.commit()


def operator_for_token(db: Session, device: TrustedDevice | None, token: str | None):
    if device is None or not token or len(token) > 256:
        return None
    return db.scalar(
        select(Operator)
        .join(OperatorSession, OperatorSession.operator_id == Operator.id)
        .where(
            OperatorSession.token_hash == token_digest(token),
            OperatorSession.device_id == device.id,
            OperatorSession.binding_hash == device.binding_hash,
            Operator.active.is_(True),
        )
    )


def login_operator(db: Session, device_token: str, operator_id: str, pin: str) -> str:
    device = device_for_token(db, device_token, lock=True)
    if device is None:
        raise AppException(
            "Autentikasi perangkat berakhir. Masuk kembali sebagai perangkat.", 401
        )
    now = now_utc()
    if device.locked_until and device.locked_until > now:
        raise AppException(
            "Terlalu banyak PIN salah. Perangkat dikunci sementara selama 5 menit.", 429
        )
    if device.locked_until:
        device.pin_failures = 0
        device.locked_until = None
    valid_id = bool(re.fullmatch(r"[0-9]{1,10}", operator_id or ""))
    valid_id = valid_id and int(operator_id) <= 2147483647
    operator = None
    if valid_id:
        operator = db.scalar(
            select(Operator)
            .where(Operator.id == int(operator_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    valid_pin = re.fullmatch(r"[0-9]{6}", pin or "") is not None
    valid = (
        verify_secret(operator.pin_hash if operator else None, pin)
        if valid_pin
        else False
    )
    if not valid or operator is None or not operator.active:
        device.pin_failures = min(MAX_PIN_FAILURES, device.pin_failures + 1)
        if device.pin_failures == MAX_PIN_FAILURES:
            device.locked_until = now + PIN_LOCKOUT
        db.commit()  # Failed attempts must survive the error response.
        if device.locked_until:
            raise AppException(
                "Terlalu banyak PIN salah. Perangkat dikunci selama 5 menit.", 429
            )
        raise AppException(
            "Operator atau PIN tidak valid. PIN harus terdiri dari 6 digit.", 401
        )
    device.pin_failures = 0
    device.locked_until = None
    if password_hasher.check_needs_rehash(operator.pin_hash):
        operator.pin_hash = hash_password(pin)
    db.execute(delete(OperatorSession).where(OperatorSession.device_id == device.id))
    token = token_urlsafe(32)
    db.add(
        OperatorSession(
            token_hash=token_digest(token),
            operator_id=operator.id,
            device_id=device.id,
            binding_hash=device.binding_hash,
        )
    )
    db.commit()
    return token


def logout_operator(db: Session, device_token: str | None, operator_token: str | None):
    device = device_for_token(db, device_token, lock=True)
    if device and operator_token:
        db.execute(
            delete(OperatorSession).where(
                OperatorSession.device_id == device.id,
                OperatorSession.token_hash == token_digest(operator_token),
            )
        )
    db.commit()
