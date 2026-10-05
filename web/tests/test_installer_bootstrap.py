"""Installer account creation must never reset or duplicate an existing admin."""

from app.models.admin import Admin
from app.services.admin_auth_service import bootstrap_first_admin, password_hasher
from sqlalchemy import select


def test_first_bootstrap_uses_application_password_hash(db_session):
    admin = bootstrap_first_admin(
        db_session, " School-Admin ", "first private password"
    )
    assert admin.username == "school-admin"
    assert password_hasher.verify(admin.password_hash, "first private password")
    assert admin.password_hash != "first private password"


def test_repeated_bootstrap_keeps_hash_even_with_different_username(db_session):
    admin = bootstrap_first_admin(db_session, "admin", "first private password")
    original = admin.password_hash
    assert bootstrap_first_admin(db_session, "admin", "replacement password") is None
    assert (
        bootstrap_first_admin(db_session, "other-admin", "replacement password") is None
    )
    assert list(db_session.scalars(select(Admin))) == [admin]
    assert admin.password_hash == original


def test_inactive_admin_is_not_reactivated_by_installer(db_session):
    admin = bootstrap_first_admin(db_session, "admin", "first private password")
    admin.active = False
    db_session.commit()
    assert bootstrap_first_admin(db_session, "admin", "replacement password") is None
    db_session.refresh(admin)
    assert not admin.active
