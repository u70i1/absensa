"""Password verification and opaque, database-backed admin sessions."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from app.models.admin import Admin, AdminSession
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

password_hasher = PasswordHasher()
_DUMMY_PASSWORD_HASH = password_hasher.hash(token_urlsafe(32))


def normalize_username(username: str) -> str:
    return username.strip().casefold()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def authenticate_admin(db: Session, username: str, password: str) -> Admin | None:
    admin = db.scalar(
        select(Admin).where(Admin.username == normalize_username(username))
    )
    password_hash = admin.password_hash if admin is not None else _DUMMY_PASSWORD_HASH
    try:
        password_valid = password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        password_valid = False

    if admin is None or not admin.active or not password_valid:
        return None

    if password_hasher.check_needs_rehash(admin.password_hash):
        admin.password_hash = hash_password(password)
        db.commit()
    return admin


def _token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_admin_session(db: Session, admin: Admin, lifetime_hours: int) -> str:
    token = token_urlsafe(32)
    db.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id))
    db.add(
        AdminSession(
            token_hash=_token_digest(token),
            admin_id=admin.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=lifetime_hours),
        )
    )
    db.commit()
    return token


def admin_for_session(db: Session, token: str | None) -> Admin | None:
    if not token:
        return None
    session = db.scalar(
        select(AdminSession)
        .join(AdminSession.admin)
        .where(
            AdminSession.token_hash == _token_digest(token),
            AdminSession.expires_at > datetime.now(timezone.utc),
            Admin.active.is_(True),
        )
    )
    return session.admin if session is not None else None


def delete_admin_session(db: Session, token: str | None) -> None:
    if not token:
        return
    db.execute(
        delete(AdminSession).where(AdminSession.token_hash == _token_digest(token))
    )
    db.commit()


def set_admin_credentials(db: Session, username: str, password: str) -> Admin:
    normalized_username = normalize_username(username)
    admin = db.scalar(select(Admin).where(Admin.username == normalized_username))
    if admin is None:
        admin = Admin(
            username=normalized_username, password_hash=hash_password(password)
        )
        db.add(admin)
    else:
        admin.password_hash = hash_password(password)
        admin.active = True
        db.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id))
    db.commit()
    db.refresh(admin)
    return admin
