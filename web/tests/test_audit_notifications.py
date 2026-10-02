"""Changes while a notification batch waits must be revalidated before sending."""

from datetime import timedelta

import pytest
from app.models.student import Student
from app.models.whatsapp_notification import WhatsAppNotificationSettings
from app.services import whatsapp_notification_service as service
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from tests.test_whatsapp_notifications import AT, FakeGateway, configure, contact


@pytest.mark.parametrize(
    "change", ["deactivate", "delete", "clear_phone", "new_phone", "rename"]
)
def test_recipient_changes_during_delay(
    db_session, existing_student, student_factory, change
):
    contact(existing_student, db_session, "628111111111")
    later = contact(
        student_factory(name="Later", nisn="9900000091"), db_session, "628222222222"
    )
    later_id = later.id
    configure(db_session, safe_mode=True)
    gateway = FakeGateway()

    def during_delay(_):
        if change == "delete":
            db_session.execute(delete(Student).where(Student.id == later_id))
        else:
            values = {
                "deactivate": {"current": False},
                "clear_phone": {"guardian_phone": None},
                "new_phone": {"guardian_phone": "628333333333"},
                "rename": {"name": "Renamed"},
            }[change]
            db_session.execute(
                update(Student).where(Student.id == later_id).values(**values)
            )
        db_session.commit()

    result = service.run_daily(db_session, gateway, at=AT, sleep=during_delay)
    if change in {"deactivate", "delete", "clear_phone"}:
        assert result["sent"] == 1
    else:
        assert result["sent"] == 2
        assert gateway.messages[-1] == (
            "628333333333" if change == "new_phone" else "628222222222",
            "Halo Renamed dari -" if change == "rename" else "Halo Later dari -",
        )


def test_batch_stops_at_school_midnight(db_session, existing_student, student_factory):
    contact(existing_student, db_session, "628111111111")
    contact(student_factory(nisn="9900000092"), db_session, "628222222222")
    configure(db_session, safe_mode=True)
    gateway = FakeGateway()
    at = AT.replace(hour=23, minute=59, second=50)
    result = service.run_daily(
        db_session,
        gateway,
        at=at,
        sleep=lambda _: None,
        clock=lambda: at if not gateway.messages else at + timedelta(seconds=30),
    )
    assert result == {"state": "interrupted", "sent": 1, "failed": 0}


def test_old_manual_reservation_cannot_start_next_day(db_session, existing_student):
    contact(existing_student, db_session, "628111111111")
    configure(db_session)
    gateway = FakeGateway()
    reserved = service.run_daily(
        db_session, gateway, manual=True, prepare_only=True, at=AT
    )
    result = service.run_daily(
        db_session,
        gateway,
        manual=True,
        reserved_run_id=reserved["run_id"],
        at=AT + timedelta(days=1),
    )
    assert result["state"] == "reservation_expired"
    assert gateway.messages == []


def test_settings_refresh_after_another_process_updates_them(engine):
    with Session(engine) as reader, Session(engine) as writer:
        config = service.get_settings(reader)
        original = config.enabled
        try:
            writer.execute(
                update(WhatsAppNotificationSettings)
                .where(WhatsAppNotificationSettings.id == 1)
                .values(enabled=not original)
            )
            writer.commit()
            assert service.get_settings(reader).enabled is not original
        finally:
            reader.rollback()
            writer.execute(
                update(WhatsAppNotificationSettings)
                .where(WhatsAppNotificationSettings.id == 1)
                .values(enabled=original)
            )
            writer.commit()
