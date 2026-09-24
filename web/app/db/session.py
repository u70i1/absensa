"""Reusable database session, includes engine and get_db()"""

from collections.abc import Generator

from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

engine = create_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy database session and ensure it is closed afterward.

    Yields:
        Session: SQLAlchemy session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
