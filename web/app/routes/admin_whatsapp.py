"""Admin controls for the WhatsApp connection and absence notifications."""

from datetime import time
from typing import Annotated

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.routes.admin import render_modal
from app.services import whatsapp_notification_service as notifications
from app.services.whatsapp_gateway_service import GatewayProblem, WhatsAppGateway
from app.templating import templates
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, sessionmaker

router = APIRouter(prefix="/admin/whatsapp", dependencies=[Depends(require_admin)])


def get_gateway() -> WhatsAppGateway:
    return WhatsAppGateway(settings.whatsapp_bridge_url, settings.whatsapp_bridge_token)


Gateway = Annotated[WhatsAppGateway, Depends(get_gateway)]
Database = Annotated[Session, Depends(get_db)]
NOTICES = {
    "settings": "Pengaturan notifikasi disimpan.",
    "enabled": "Layanan notifikasi otomatis diaktifkan.",
    "disabled": "Layanan notifikasi otomatis dinonaktifkan.",
    "sent": "Pengiriman notifikasi hari ini dimulai. Muat ulang halaman untuk melihat statusnya.",
    "skipped": "Notifikasi hari ini dilewati.",
    "restored": "Notifikasi hari ini kembali mengikuti jadwal.",
    "test": "Pesan uji berhasil dikirim.",
    "disconnected": "Koneksi WhatsApp diputuskan.",
}


def render_page(
    request: Request,
    gateway: WhatsAppGateway,
    db: Session,
    *,
    error: str | None = None,
    test_number_value: str = "",
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="admin/pages/whatsapp.html",
        context={
            "status": gateway.status(),
            "config": notifications.get_settings(db),
            "daily": notifications.daily_state(db),
            "error": error,
            "test_number_value": test_number_value,
            "notice": NOTICES.get(request.query_params.get("notice")),
        },
        status_code=status_code,
    )


def _failure(
    request: Request,
    gateway: WhatsAppGateway,
    db: Session,
    exc: Exception,
    *,
    test_number_value: str = "",
):
    return render_page(
        request,
        gateway,
        db,
        error=exc.detail,
        test_number_value=test_number_value,
        status_code=exc.status_code,
    )


@router.get("", name="admin_whatsapp")
def dashboard(request: Request, gateway: Gateway, db: Database):
    return render_page(request, gateway, db)


@router.get("/config", name="admin_whatsapp_config")
def config_json(db: Database):
    config = notifications.get_settings(db)
    return {
        "enabled": config.enabled,
        "send_time": config.send_time.isoformat(timespec="minutes"),
        "minimum_attendance": config.minimum_attendance,
        "message_template": config.message_template,
        "safe_mode": config.safe_mode,
        "today": notifications.daily_state(db),
    }


@router.get("/daily", name="admin_whatsapp_daily")
def daily_fragment(request: Request, db: Database):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/admin/whatsapp", status_code=303)
    response = templates.TemplateResponse(
        request=request,
        name="admin/components/whatsapp-actions.html",
        context={"daily": notifications.daily_state(db)},
    )
    response.headers["Vary"] = "HX-Request"
    return response


@router.get("/confirm/{action}", name="admin_whatsapp_confirmation")
def confirmation(request: Request, action: str, db: Database, gateway: Gateway):
    if action not in {"send-now", "skip-today", "enable", "disable", "disconnect"}:
        raise HTTPException(404)
    config = notifications.get_settings(db)
    daily = notifications.daily_state(db)
    if (
        action == "send-now"
        and not daily["can_send_now"]
        or action == "skip-today"
        and not daily["can_skip"]
    ):
        raise HTTPException(409, daily["reason"])
    if (
        action == "enable"
        and config.enabled
        or action == "disable"
        and not config.enabled
    ):
        raise HTTPException(409, "Status layanan telah berubah.")
    if action == "disconnect" and gateway.status().state != "connected":
        raise HTTPException(409, "WhatsApp belum terhubung.")
    return render_modal(
        request,
        "modals/whatsapp-confirm.html",
        {
            "action": action,
            "daily": daily,
            "back_url": "/admin/whatsapp",
            "back_label": "Kembali ke WhatsApp Gateway",
            "dialog_title": "Konfirmasi WhatsApp",
        },
    )


@router.get("/status", name="admin_whatsapp_status")
def status_fragment(request: Request, gateway: Gateway):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/admin/whatsapp", status_code=303)
    response = templates.TemplateResponse(
        request=request,
        name="admin/components/whatsapp-status.html",
        context={"status": gateway.status()},
    )
    response.headers["Vary"] = "HX-Request"
    return response


@router.post("/connect", name="admin_whatsapp_connect")
def connect(request: Request, gateway: Gateway, db: Database):
    try:
        gateway.connect()
    except GatewayProblem as exc:
        return _failure(request, gateway, db, exc)
    return RedirectResponse("/admin/whatsapp", status_code=303)


@router.post("/disconnect", name="admin_whatsapp_disconnect")
def disconnect(request: Request, gateway: Gateway, db: Database):
    try:
        gateway.disconnect()
    except GatewayProblem as exc:
        return _failure(request, gateway, db, exc)
    return RedirectResponse("/admin/whatsapp?notice=disconnected", status_code=303)


@router.post("/settings", name="admin_whatsapp_settings")
def update_settings(
    request: Request,
    gateway: Gateway,
    db: Database,
    send_time: time = Form(...),
    minimum_attendance: int = Form(...),
    message_template: str = Form(...),
    safe_mode: bool = Form(False),
):
    try:
        notifications.update_settings(
            db,
            send_time=send_time,
            minimum_attendance=minimum_attendance,
            message_template=message_template,
            safe_mode=safe_mode,
        )
    except notifications.NotificationProblem as exc:
        return _failure(request, gateway, db, exc)
    return RedirectResponse("/admin/whatsapp?notice=settings", status_code=303)


@router.post("/enabled", name="admin_whatsapp_enabled")
def set_enabled(db: Database, enabled: bool = Form(...)):
    notifications.set_enabled(db, enabled)
    return RedirectResponse(
        f"/admin/whatsapp?notice={'enabled' if enabled else 'disabled'}",
        status_code=303,
    )


@router.post("/test", name="admin_whatsapp_test")
def send_test(
    request: Request, gateway: Gateway, db: Database, test_number: str = Form("")
):
    try:
        notifications.send_test(db, gateway, test_number)
    except (GatewayProblem, notifications.NotificationProblem) as exc:
        return _failure(
            request,
            gateway,
            db,
            exc,
            test_number_value=test_number[:32],
        )
    return RedirectResponse("/admin/whatsapp?notice=test", status_code=303)


def _send_reserved(run_id: int, bind, gateway: WhatsAppGateway) -> None:
    with sessionmaker(bind=bind, join_transaction_mode="create_savepoint")() as db:
        notifications.run_daily(db, gateway, manual=True, reserved_run_id=run_id)


@router.post("/send-now", name="admin_whatsapp_send_now")
def send_now(
    request: Request, background_tasks: BackgroundTasks, gateway: Gateway, db: Database
):
    try:
        result = notifications.run_daily(db, gateway, manual=True, prepare_only=True)
    except notifications.NotificationProblem as exc:
        return _failure(request, gateway, db, exc)
    if result["state"] != "queued":
        return _failure(
            request,
            gateway,
            db,
            notifications.NotificationProblem(
                "Pengiriman hari ini tidak dapat dijalankan saat ini."
            ),
        )
    background_tasks.add_task(_send_reserved, result["run_id"], db.get_bind(), gateway)
    return RedirectResponse("/admin/whatsapp?notice=sent", status_code=303)


@router.post("/skip-today", name="admin_whatsapp_skip_today")
def skip_today(request: Request, gateway: Gateway, db: Database):
    try:
        notifications.skip_today(db)
    except notifications.NotificationProblem as exc:
        return _failure(request, gateway, db, exc)
    return RedirectResponse("/admin/whatsapp?notice=skipped", status_code=303)


@router.post("/cancel-skip", name="admin_whatsapp_cancel_skip")
def cancel_skip(request: Request, gateway: Gateway, db: Database):
    try:
        notifications.skip_today(db, cancel=True)
    except notifications.NotificationProblem as exc:
        return _failure(request, gateway, db, exc)
    return RedirectResponse("/admin/whatsapp?notice=restored", status_code=303)
