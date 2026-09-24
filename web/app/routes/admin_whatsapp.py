"""WhatsApp bridge controls for authenticated administrators."""

from typing import Annotated

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.services.whatsapp_gateway_service import GatewayProblem, WhatsAppGateway
from app.templating import templates
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/admin/whatsapp", dependencies=[Depends(require_admin)])


def get_gateway() -> WhatsAppGateway:
    return WhatsAppGateway(settings.whatsapp_bridge_url, settings.whatsapp_bridge_token)


Gateway = Annotated[WhatsAppGateway, Depends(get_gateway)]


def render_page(
    request: Request,
    gateway: WhatsAppGateway,
    *,
    error: str | None = None,
    phone_value: str = "",
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="admin/pages/whatsapp.html",
        context={
            "status": gateway.status(),
            "error": error,
            "phone_value": phone_value,
            "sent": request.query_params.get("sent") == "1",
        },
        status_code=status_code,
    )


@router.get("", name="admin_whatsapp")
def dashboard(request: Request, gateway: Gateway):
    return render_page(request, gateway)


@router.get("/status", name="admin_whatsapp_status")
def status_fragment(request: Request, gateway: Gateway):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/admin/whatsapp", status_code=303)
    response = templates.TemplateResponse(
        request=request,
        name="admin/components/whatsapp-status.html",
        context={"status": gateway.status(), "phone_value": ""},
    )
    response.headers["Vary"] = "HX-Request"
    return response


@router.post("/connect", name="admin_whatsapp_connect")
def connect(request: Request, gateway: Gateway):
    try:
        gateway.connect()
    except GatewayProblem as exc:
        return render_page(
            request, gateway, error=exc.detail, status_code=exc.status_code
        )
    return RedirectResponse("/admin/whatsapp", status_code=303)


@router.post("/send", name="admin_whatsapp_send")
def send_test(request: Request, gateway: Gateway, phone: str = Form("")):
    try:
        gateway.send_test(phone)
    except GatewayProblem as exc:
        return render_page(
            request,
            gateway,
            error=exc.detail,
            phone_value=phone[:32],
            status_code=exc.status_code,
        )
    return RedirectResponse("/admin/whatsapp?sent=1", status_code=303)
