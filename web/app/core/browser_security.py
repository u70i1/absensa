"""Fail-closed same-origin CSRF checks for cookie-authenticated mutations."""

from urllib.parse import urlsplit

from app.core.config import settings
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

DEVICE_COOKIE_SECONDS = (
    400 * 24 * 60 * 60
)  # Browser limit; refreshed during authenticated use.


def origin_tuple(value):
    try:
        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
        ):
            return None
        return (
            url.scheme,
            url.hostname.lower(),
            url.port or (443 if url.scheme == "https" else 80),
        )
    except ValueError:
        return None


def set_device_cookie(response, token):
    from app.core.access_auth import DEVICE_COOKIE

    response.set_cookie(
        DEVICE_COOKIE,
        token,
        max_age=DEVICE_COOKIE_SECONDS,
        path="/",
        secure=settings.access_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_access_cookies(response, *, device=False):
    from app.core.access_auth import DEVICE_COOKIE, OPERATOR_COOKIE

    for name in [DEVICE_COOKIE, OPERATOR_COOKIE] if device else [OPERATOR_COOKIE]:
        response.delete_cookie(
            name,
            path="/",
            secure=settings.access_cookie_secure,
            httponly=True,
            samesite="lax",
        )


class BrowserSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            # Modern form/HTMX/fetch requests send Origin. Referer covers older
            # same-origin clients. Missing, null, foreign or malformed origins fail closed.
            source = request.headers.get("origin") or request.headers.get("referer")
            source_origin = origin_tuple(source) if source else None
            if (
                request.headers.get("sec-fetch-site") == "cross-site"
                or not source
                or source_origin is None
                or source_origin != origin_tuple(str(request.url))
            ):
                return JSONResponse(
                    {
                        "detail": "Permintaan harus berasal dari halaman Absensa yang sama. Muat ulang halaman lalu coba lagi."
                    },
                    status_code=403,
                )
        response = await call_next(request)
        if request.url.path != "/admin/static" and not request.url.path.startswith(
            "/admin/static/"
        ):
            response.headers.setdefault("Cache-Control", "no-store")
        token = getattr(request.state, "renew_device_token", None)
        if token and not getattr(request.state, "clear_device_cookie", False):
            set_device_cookie(response, token)
        return response
