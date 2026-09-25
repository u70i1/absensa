"""Small server-to-server client for the local WhatsApp bridge."""

import re
from dataclasses import dataclass
from typing import Literal

import httpx

GatewayState = Literal[
    "disconnected",
    "disconnecting",
    "starting",
    "qr",
    "connected",
    "error",
    "unavailable",
]
STATES = {"disconnected", "disconnecting", "starting", "qr", "connected", "error"}
QR_IMAGE = re.compile(r"data:image/png;base64,[A-Za-z0-9+/=]+\Z")


class GatewayProblem(Exception):
    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class GatewayStatus:
    state: GatewayState
    phone: str | None = None
    qr_data_url: str | None = None
    detail: str | None = None


def normalize_phone(value: str) -> str:
    compact = re.sub(r"[\s()\-]", "", value.strip())
    if not re.fullmatch(r"\+?[1-9][0-9]{7,14}", compact):
        raise GatewayProblem(
            "Masukkan nomor dengan kode negara, misalnya +6281234567890.", 422
        )
    return compact.removeprefix("+")


class WhatsAppGateway:
    def __init__(
        self,
        base_url: str,
        token: str,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.transport = transport

    def _request(self, method: str, path: str, *, json: dict | None = None) -> dict:
        if not self.token or self.token.startswith("replace-with-"):
            raise GatewayProblem("Kunci layanan WhatsApp belum dikonfigurasi.", 503)
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30 if path == "api/messages" else 5,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = client.request(method, path.lstrip("/"), json=json)
        except httpx.RequestError as exc:
            raise GatewayProblem(
                "Layanan WhatsApp tidak dapat dihubungi.", 503
            ) from exc

        if response.status_code in (401, 403):
            raise GatewayProblem("Kunci layanan WhatsApp tidak cocok.", 503)
        try:
            payload = response.json()
        except ValueError as exc:
            raise GatewayProblem("Respons layanan WhatsApp tidak valid.") from exc
        if not isinstance(payload, dict):
            raise GatewayProblem("Respons layanan WhatsApp tidak valid.")
        if response.is_error:
            code = payload.get("error")
            if code == "not_connected":
                raise GatewayProblem("WhatsApp belum terhubung.", 409)
            if code == "disconnecting":
                raise GatewayProblem("Pemutusan koneksi masih berlangsung.", 409)
            if code == "number_not_registered":
                raise GatewayProblem("Nomor tersebut belum terdaftar di WhatsApp.", 422)
            if code == "invalid_phone":
                raise GatewayProblem("Nomor telepon tidak valid.", 422)
            raise GatewayProblem("Layanan WhatsApp gagal memproses permintaan.")
        return payload

    def status(self) -> GatewayStatus:
        try:
            payload = self._request("GET", "api/status")
            state = payload.get("state")
            if state not in STATES:
                raise GatewayProblem("Status layanan WhatsApp tidak valid.")
            if state == "qr" and payload.get("qr_available"):
                payload = self._request("GET", "api/qr")
                state = payload.get("state")
                if state not in STATES:
                    raise GatewayProblem("Status layanan WhatsApp tidak valid.")
            qr_data_url = payload.get("qr_data_url")
            if (
                not isinstance(qr_data_url, str)
                or len(qr_data_url) > 100_000
                or not QR_IMAGE.fullmatch(qr_data_url)
            ):
                qr_data_url = None
            phone = payload.get("phone")
            if not isinstance(phone, str) or not re.fullmatch(r"[0-9]{8,15}", phone):
                phone = None
            return GatewayStatus(state=state, phone=phone, qr_data_url=qr_data_url)
        except GatewayProblem as exc:
            return GatewayStatus(state="unavailable", detail=exc.detail)

    def connect(self) -> None:
        self._request("POST", "api/connect")

    def disconnect(self) -> None:
        self._request("POST", "api/disconnect")

    def send_message(self, phone: str, message: str) -> None:
        if not message.strip() or len(message) > 4000:
            raise GatewayProblem("Pesan WhatsApp tidak valid.", 422)
        self._request(
            "POST",
            "api/messages",
            json={"phone": normalize_phone(phone), "message": message},
        )
