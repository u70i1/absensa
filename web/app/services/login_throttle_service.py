"""Reserve login attempts atomically before Argon2, across application workers."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import ceil

from app.models.login_throttle import LoginThrottle
from app.services.exceptions import AppException
from sqlalchemy import case, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

WINDOW = timedelta(minutes=5)
ACCOUNT_ATTEMPTS = 5
SOURCE_ATTEMPTS = 30


class LoginThrottled(AppException):
    def __init__(self, retry_after: int):
        super().__init__(
            "Terlalu banyak percobaan masuk. Coba lagi beberapa menit kemudian.", 429
        )
        self.retry_after = retry_after


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def reserve_attempt(db: Session, realm: str, username: str, source: str) -> None:
    now = now_utc()
    budgets = [
        (sha256(f"{realm}:source:{source}".encode()).hexdigest(), SOURCE_ATTEMPTS),
        (
            sha256(
                f"{realm}:account:{username.strip().casefold()}".encode()
            ).hexdigest(),
            ACCOUNT_ATTEMPTS,
        ),
    ]
    retry_after = 0
    # Reserve source before account on every request. A blocked source must not
    # create unlimited buckets by submitting arbitrary usernames.
    for key, limit in budgets:
        expired = LoginThrottle.expires_at <= now
        row = db.execute(
            insert(LoginThrottle)
            .values(key=key, attempts=1, expires_at=now + WINDOW)
            .on_conflict_do_update(
                index_elements=[LoginThrottle.key],
                set_={
                    "attempts": case(
                        (expired, 1),
                        else_=func.least(LoginThrottle.attempts + 1, limit + 1),
                    ),
                    "expires_at": case(
                        (expired, now + WINDOW), else_=LoginThrottle.expires_at
                    ),
                },
            )
            .returning(LoginThrottle.attempts, LoginThrottle.expires_at)
        ).one()
        if row.attempts > limit:
            retry_after = max(retry_after, ceil((row.expires_at - now).total_seconds()))
            break
    # Prune only expired budgets; active attempts survive process restarts.
    db.execute(delete(LoginThrottle).where(LoginThrottle.expires_at < now - WINDOW))
    db.commit()
    if retry_after:
        raise LoginThrottled(max(1, retry_after))
