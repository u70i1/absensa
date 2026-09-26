"""Business rules for scheduled, manual, skipped and test notifications."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.models.whatsapp_notification import DEFAULT_MESSAGE_TEMPLATE
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


def test_test_message_requires_a_student(db_session):
    configure(db_session, enabled=False, minimum=100)
    with pytest.raises(service.NotificationProblem, match="Belum ada siswa"):
        service.send_test(db_session, FakeGateway(), "08111111111", at=AT)


def test_test_message_uses_real_student_without_changing_daily_state(
    db_session, existing_student
):
    configure(db_session, enabled=False, minimum=100)
    gateway = FakeGateway()
    assert (
        service.send_test(db_session, gateway, "08111111111", at=AT)["student_id"]
        == existing_student.id
    )
    assert gateway.messages == [("628111111111", "Halo Nicholas Angle dari 11B")]
    assert service.daily_state(db_session, AT)["state"] == "ready"
    assert db_session.scalar(select(Log).where(Log.kind == "test")).status == "sent"


def test_test_number_is_validated_and_not_logged(db_session, existing_student):
    configure(db_session)
    with pytest.raises(GatewayProblem):
        service.send_test(db_session, FakeGateway(), "not-a-number", at=AT)
    assert db_session.scalars(select(Log).where(Log.kind == "test")).all() == []


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


def test_safe_mode_skips_students_without_contacts_without_waiting(
    db_session, existing_student, student_factory
):
    contact(existing_student, db_session, "+628111111111")
    student_factory(name="No contact", nisn="1111111111")
    configure(db_session, safe_mode=True, delay=30)
    pauses = []
    gateway = FakeGateway()

    result = service.run_daily(db_session, gateway, manual=True, at=AT, sleep=pauses.append)

    assert result == {"state": "completed", "sent": 1, "failed": 0}
    assert pauses == []
    assert len(gateway.messages) == 1


def test_safe_mode_resume_does_not_wait_for_previously_claimed_students(
    db_session, existing_student, student_factory
):
    contact(existing_student, db_session, "+628111111111")
    later = contact(
        student_factory(name="Later", nisn="1111111111"),
        db_session,
        "+628222222222",
    )
    configure(db_session, safe_mode=True, delay=30)
    service._claim(db_session, AT.date(), existing_student.id)
    pauses = []
    gateway = FakeGateway()

    result = service.run_daily(db_session, gateway, manual=True, at=AT, sleep=pauses.append)

    assert result["state"] == "completed_with_failures"
    assert gateway.messages == [("628222222222", "Halo Later dari -")]
    assert pauses == []
    assert db_session.scalar(select(Log).where(Log.student_id == later.id)).status == "sent"


def test_shared_guardian_receives_a_separate_message_for_each_absent_student(
    db_session, existing_student, student_factory
):
    guardian = "08111111111"
    contact(existing_student, db_session, guardian)
    other = contact(
        student_factory(
            name="Sibling", nisn="1111111111", class_id=existing_student.class_id
        ),
        db_session,
        guardian,
    )
    configure(db_session, safe_mode=True, delay=30)
    pauses = []
    gateway = FakeGateway()

    result = service.run_daily(
        db_session, gateway, manual=True, at=AT, sleep=pauses.append
    )

    assert result == {"state": "completed", "sent": 2, "failed": 0}
    assert pauses == [30]
    assert gateway.messages == [
        ("628111111111", "Halo Nicholas Angle dari 11B"),
        ("628111111111", "Halo Sibling dari 11B"),
    ]
    deliveries = db_session.scalars(select(Log).where(Log.kind == "delivery")).all()
    assert {delivery.student_id for delivery in deliveries} == {
        existing_student.id,
        other.id,
    }
    assert (
        service.run_daily(db_session, gateway, manual=True, at=AT)["state"]
        == "already_run"
    )
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
    assert result == {"state": "completed_with_failures", "sent": 1, "failed": 2}
    assert len(gateway.messages) == 1
    assert len(db_session.scalars(select(Log).where(Log.kind == "delivery")).all()) == 3


def test_gateway_failure_pauses_scheduler_until_manual_review(
    db_session, existing_student, student_factory
):
    contact(existing_student, db_session, "+628111111111")
    contact(
        student_factory(name="Later", nisn="1111111111"),
        db_session,
        "+628222222222",
    )
    configure(db_session, enabled=False, minimum=20)

    class Unavailable(FakeGateway):
        def send_message(self, phone, message):
            raise GatewayProblem("Layanan WhatsApp tidak dapat dihubungi.", 502)

    first = service.run_daily(db_session, Unavailable(), manual=True, at=AT)
    assert first == {"state": "needs_attention", "sent": 0, "failed": 1}
    assert service.daily_state(db_session, AT)["can_send_now"] is True
    gateway = FakeGateway()
    assert service.run_daily(db_session, gateway, at=AT)["state"] == "needs_attention"
    assert gateway.messages == []
    resumed = service.run_daily(db_session, gateway, manual=True, at=AT)
    assert resumed == {"state": "completed_with_failures", "sent": 1, "failed": 0}
    assert gateway.messages == [("628222222222", "Halo Later dari -")]
    assert service.daily_state(db_session, AT)["failed"] == 1


def test_legacy_completed_run_with_failed_delivery_is_shown_as_partial(
    db_session, existing_student
):
    contact(existing_student, db_session, "+628111111111")
    configure(db_session)
    gateway = FakeGateway(fail_phone="628111111111")
    result = service.run_daily(db_session, gateway, manual=True, at=AT)
    assert result["state"] == "completed_with_failures"

    run = db_session.scalar(select(Log).where(Log.kind == "run"))
    run.status = "completed"  # Rows written before partial completion existed.
    db_session.commit()
    assert service.daily_state(db_session, AT)["state"] == "completed_with_failures"
    assert service.daily_state(db_session, AT)["can_send_now"] is False


def test_scheduler_recovers_an_expired_manual_batch_with_shared_guardian(
    db_session, existing_student, student_factory
):
    guardian = "08111111111"
    contact(existing_student, db_session, guardian)
    contact(student_factory(name="Sibling", nisn="1111111111"), db_session, guardian)
    configure(db_session, enabled=False, minimum=20)
    gateway = FakeGateway()
    queued = service.run_daily(
        db_session, gateway, manual=True, at=AT.replace(hour=7), prepare_only=True
    )
    assert queued["state"] == "queued"

    # Simulate the FastAPI process stopping before its background task starts.
    run = db_session.get(Log, queued["run_id"])
    run.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    recovered = service.run_daily(db_session, gateway, at=AT.replace(hour=7))
    assert recovered == {"state": "completed", "sent": 2, "failed": 0}
    assert [phone for phone, _message in gateway.messages] == ["628111111111"] * 2


def test_manual_retry_marks_an_older_unfinished_run_for_recovery(
    db_session, existing_student
):
    contact(existing_student, db_session, "08111111111")
    configure(db_session, enabled=False)
    gateway = FakeGateway()
    queued = service.run_daily(
        db_session, gateway, manual=True, at=AT, prepare_only=True
    )
    run = db_session.get(Log, queued["run_id"])
    run.detail = None  # Rows created before manual runs recorded their origin.
    run.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    resumed = service.run_daily(
        db_session, gateway, manual=True, at=AT, prepare_only=True
    )
    assert resumed["state"] == "queued"
    assert db_session.get(Log, queued["run_id"]).detail == "manual"


@pytest.mark.parametrize(
    "template",
    ["{{unknown}}", "{{nama", "{{ nama + 1 }}", "{% include 'secret' %}", ""],
)
def test_invalid_templates_are_rejected(template):
    with pytest.raises(service.NotificationProblem):
        service.validate_template(template)


def test_template_variables_are_replaced_without_executing_code():
    assert service.render_message("{{nama}} / {{ kelas }}", "A & B", "X") == "A & B / X"


def test_default_template_matches_school_copy_and_renders_student_name():
    assert DEFAULT_MESSAGE_TEMPLATE == (
        "Selamat siang Bapak/Ibu Orang Tua/Wali {{nama_siswa}} ({{kelas}}),\n\n"
        "Informasi presensi hari ini menunjukkan {{nama_siswa}} tidak hadir di sekolah.\n\n"
        "_Catatan: Pesan otomatis ini dikirim sebagai konfirmasi harian. "
        "Jika izin/keterangan sudah disampaikan kepada Wali Kelas, "
        "silakan abaikan pesan ini. Terima kasih._"
    )
    assert (
        service.render_message(DEFAULT_MESSAGE_TEMPLATE, "Ayu", "VII-A").count("Ayu")
        == 2
    )
