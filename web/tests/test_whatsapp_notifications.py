"""Business rules for scheduled, manual, skipped and test notifications."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.models.whatsapp_notification import WhatsAppNotificationLog as Log
from app.services import whatsapp_notification_service as service
from app.services.whatsapp_gateway_service import GatewayProblem, GatewayStatus
from sqlalchemy import select

AT = datetime(2026, 9, 24, 9, 30, tzinfo=ZoneInfo(settings.timezone))


class FakeGateway:
    def __init__(self, *, fail_phone=None):
        self.messages = []
        self.fail_phone = fail_phone

    def status(self):
        return GatewayStatus(state="connected")

    def send_message(self, phone, message):
        if phone == self.fail_phone:
            raise GatewayProblem("Nomor tersebut belum terdaftar di WhatsApp.", 422)
        self.messages.append((phone, message))


def configure(db_session, *, enabled=True, minimum=0, safe_mode=False, delay=30):
    settings = service.get_settings(db_session)
    settings.enabled = enabled
    settings.minimum_attendance = minimum
    settings.safe_mode = safe_mode
    settings.delay_seconds = delay
    settings.message_template = "Halo {{nama}} dari {{kelas}}"
    db_session.commit()
    return settings


def contact(student, db_session, phone):
    student.guardian_phone = phone
    db_session.commit()
    return student


def test_scheduled_waits_for_service_time_and_minimum(db_session, existing_student):
    gateway = FakeGateway()
    contact(existing_student, db_session, "+628111111111")
    configure(db_session, minimum=2)
    assert (
        service.run_daily(db_session, gateway, at=AT.replace(hour=8))["state"]
        == "before_time"
    )
    assert service.run_daily(db_session, gateway, at=AT)["state"] == "below_minimum"
    assert db_session.scalars(select(Log).where(Log.kind == "run")).all() == []
    configure(db_session, enabled=False, minimum=0)
    assert service.run_daily(db_session, gateway, at=AT)["state"] == "disabled"
    assert gateway.messages == []


def test_scheduled_sends_only_absent_students_and_never_repeats(
    db_session, existing_student, student_factory, scan_log_factory
):
    absent = contact(existing_student, db_session, "+628111111111")
    present = contact(
        student_factory(name="Present", nisn="1111111111", class_id=absent.class_id),
        db_session,
        "+628222222222",
    )
    scan_log_factory(present, AT)
    configure(db_session)
    gateway = FakeGateway()
    first = service.run_daily(db_session, gateway, at=AT)
    assert first == {"state": "completed", "sent": 1, "failed": 0}
    assert gateway.messages == [("628111111111", "Halo Nicholas Angle dari 11B")]
    assert service.run_daily(db_session, gateway, at=AT)["state"] == "already_run"
    assert service.daily_state(db_session, AT)["state"] == "completed"
    with pytest.raises(service.NotificationProblem):
        service.skip_today(db_session, at=AT)


def test_skip_only_today_and_cancel_restores_scheduled_behavior(
    db_session, existing_student
):
    contact(existing_student, db_session, "+628111111111")
    configure(db_session)
    gateway = FakeGateway()
    assert service.skip_today(db_session, at=AT)["state"] == "skipped"
    assert service.run_daily(db_session, gateway, at=AT)["state"] == "skipped"
    assert (
        service.run_daily(db_session, gateway, manual=True, at=AT)["state"] == "skipped"
    )
    assert service.daily_state(db_session, AT + timedelta(days=1))["state"] == "ready"
    assert service.skip_today(db_session, cancel=True, at=AT)["state"] == "ready"
    assert service.run_daily(db_session, gateway, at=AT)["sent"] == 1


def test_manual_ignores_disabled_service_time_and_attendance_minimum(
    db_session, existing_student
):
    contact(existing_student, db_session, "+628111111111")
    configure(db_session, enabled=False, minimum=20)
    gateway = FakeGateway()
    result = service.run_daily(db_session, gateway, manual=True, at=AT.replace(hour=7))
    assert result["sent"] == 1
    assert (
        service.run_daily(db_session, gateway, manual=True, at=AT)["state"]
        == "already_run"
    )


def test_test_message_uses_real_student_without_changing_daily_state(
    db_session, existing_student
):
    configure(db_session, enabled=False, minimum=100)
    with pytest.raises(service.NotificationProblem, match="Belum ada siswa"):
        service.send_test(db_session, FakeGateway(), at=AT)
    contact(existing_student, db_session, "08111111111")
    gateway = FakeGateway()
    assert (
        service.send_test(db_session, gateway, at=AT)["student_id"]
        == existing_student.id
    )
    assert gateway.messages == [("628111111111", "Halo Nicholas Angle dari 11B")]
    assert service.daily_state(db_session, AT)["state"] == "ready"
    assert db_session.scalar(select(Log).where(Log.kind == "test")).status == "sent"


def test_safe_mode_delays_between_sends_only(
    db_session, existing_student, student_factory
):
    contact(existing_student, db_session, "+628111111111")
    contact(
        student_factory(name="Other", nisn="1111111111"), db_session, "+628222222222"
    )
    configure(db_session, safe_mode=True, delay=30)
    pauses = []
    gateway = FakeGateway()
    service.run_daily(db_session, gateway, manual=True, at=AT, sleep=pauses.append)
    assert pauses == [30]
    assert len(gateway.messages) == 2


def test_student_scanned_during_safe_mode_delay_is_not_notified(
    db_session, existing_student, student_factory, scan_log_factory
):
    contact(existing_student, db_session, "+628111111111")
    later = contact(
        student_factory(name="Later", nisn="1111111111"),
        db_session,
        "+628222222222",
    )
    configure(db_session, safe_mode=True, delay=30)
    gateway = FakeGateway()

    def during_delay(_seconds):
        scan_log_factory(later, AT)

    service.run_daily(db_session, gateway, manual=True, at=AT, sleep=during_delay)
    assert gateway.messages == [("628111111111", "Halo Nicholas Angle dari 11B")]


def test_invalid_contact_or_rejected_recipient_does_not_cancel_batch(
    db_session, existing_student, student_factory
):
    contact(existing_student, db_session, "bad number")
    contact(
        student_factory(name="Rejected", nisn="1111111111"), db_session, "+628222222222"
    )
    contact(
        student_factory(name="Good", nisn="2222222222"), db_session, "+628333333333"
    )
    configure(db_session)
    gateway = FakeGateway(fail_phone="628222222222")
    result = service.run_daily(db_session, gateway, manual=True, at=AT)
    assert result == {"state": "completed", "sent": 1, "failed": 2}
    assert len(gateway.messages) == 1
    assert len(db_session.scalars(select(Log).where(Log.kind == "delivery")).all()) == 3


def test_interrupted_run_resumes_only_unclaimed_students(
    db_session, existing_student, student_factory
):
    contact(existing_student, db_session, "+628111111111")
    contact(
        student_factory(name="Later", nisn="1111111111"),
        db_session,
        "+628222222222",
    )
    configure(db_session)

    class Unavailable(FakeGateway):
        def send_message(self, phone, message):
            raise GatewayProblem("Layanan WhatsApp tidak dapat dihubungi.", 502)

    first = service.run_daily(db_session, Unavailable(), manual=True, at=AT)
    assert first["state"] == "interrupted"
    assert service.daily_state(db_session, AT)["can_send_now"] is True
    gateway = FakeGateway()
    resumed = service.run_daily(db_session, gateway, manual=True, at=AT)
    assert resumed == {"state": "completed", "sent": 1, "failed": 0}
    assert gateway.messages == [("628222222222", "Halo Later dari -")]


@pytest.mark.parametrize(
    "template",
    ["{{unknown}}", "{{nama", "{{ nama + 1 }}", "{% include 'secret' %}", ""],
)
def test_invalid_templates_are_rejected(template):
    with pytest.raises(service.NotificationProblem):
        service.validate_template(template)


def test_template_variables_are_replaced_without_executing_code():
    assert service.render_message("{{nama}} / {{ kelas }}", "A & B", "X") == "A & B / X"
