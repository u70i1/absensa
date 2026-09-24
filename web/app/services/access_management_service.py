"""Account administration; changing secrets or disabling accounts revokes sessions."""

import re

from app.models.access import Operator, OperatorSession, TrustedDevice
from app.services.access_auth_service import revoke_binding
from app.services.admin_auth_service import hash_password, normalize_username
from app.services.exceptions import AppException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

MODELS = {"devices": TrustedDevice, "operators": Operator}


def account(db, kind, account_id, *, lock=False):
    model = MODELS.get(kind)
    if model is None:
        raise AppException("Jenis akun tidak ditemukan.", 404)
    stmt = select(model).where(model.id == account_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(stmt)
    if item is None:
        raise AppException("Akun tidak ditemukan.", 404)
    return item


def public_account(item):
    return {
        "id": item.id,
        "name": item.username if isinstance(item, TrustedDevice) else item.display_name,
        "active": item.active,
        "created_at": item.created_at,
        "bound": bool(item.binding_hash) if isinstance(item, TrustedDevice) else False,
        "bound_at": item.bound_at if isinstance(item, TrustedDevice) else None,
    }


def directory(db, kind):
    """Read only columns displayed by the dashboard, never credential hashes."""
    if kind == "devices":
        rows = db.execute(
            select(
                TrustedDevice.id,
                TrustedDevice.username.label("name"),
                TrustedDevice.active,
                TrustedDevice.created_at,
                TrustedDevice.binding_hash.is_not(None).label("bound"),
                TrustedDevice.bound_at,
            ).order_by(TrustedDevice.id)
        )
        return [dict(row._mapping) for row in rows]
    if kind == "operators":
        rows = db.execute(
            select(
                Operator.id,
                Operator.display_name.label("name"),
                Operator.active,
                Operator.created_at,
            ).order_by(Operator.id)
        )
        return [dict(row._mapping) | {"bound": False, "bound_at": None} for row in rows]
    raise AppException("Jenis akun tidak ditemukan.", 404)


def save_account(db, kind, admin_id, data, account_id=None):
    item = account(db, kind, account_id, lock=True) if account_id is not None else None
    name = str(data.get("name", "")).strip()
    if kind == "devices":
        name = normalize_username(name)
    secret = str(data.get("secret", ""))
    active = data.get("active") == "true"
    if not 1 <= len(name) <= 100:
        raise AppException("Nama wajib diisi, maksimal 100 karakter.", 422)
    if not item or secret:
        if kind == "devices" and not 8 <= len(secret) <= 1024:
            raise AppException("Kata sandi harus terdiri dari 8–1024 karakter.", 422)
        if kind == "operators" and not re.fullmatch(r"[0-9]{6}", secret):
            raise AppException("PIN wajib berisi tepat 6 digit angka.", 422)
    if item is None:
        item = MODELS[kind](created_by=admin_id)
        db.add(item)
    if kind == "devices":
        item.username = name
        if secret:
            item.password_hash = hash_password(secret)
        if account_id is not None and (secret or not active):
            revoke_binding(db, item)
    else:
        item.display_name = name
        if secret:
            item.pin_hash = hash_password(secret)
        if account_id is not None and (secret or not active):
            db.execute(
                delete(OperatorSession).where(OperatorSession.operator_id == item.id)
            )
    item.active = active
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppException("Nama pengguna perangkat sudah digunakan.", 409) from exc
    return item


def manage_account(db, kind, account_id, action):
    item = account(db, kind, account_id, lock=True)
    if action == "revoke" and kind == "devices":
        revoke_binding(db, item)
    elif action == "delete":
        db.delete(item)
    else:
        raise AppException("Tindakan tidak ditemukan.", 404)
    db.commit()
