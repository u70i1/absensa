from app.core.access_auth import AccessAuthenticationRequired
from app.core.admin_auth import AdminAuthenticationRequired
from app.core.browser_security import BrowserSecurityMiddleware, clear_access_cookies
from app.core.config import settings
from app.routes import api_router
from app.services.exceptions import AppException
from app.templating import APP_DIR, templates
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(title="absensa")
app.mount("/admin/static", StaticFiles(directory=APP_DIR / "static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(BrowserSecurityMiddleware)


# Public entry point; protected destinations handle their own login flow.
@app.get("/", name="home")
def root(request: Request):
    return templates.TemplateResponse(request=request, name="public/index.html")


app.include_router(api_router)


@app.exception_handler(AdminAuthenticationRequired)
async def admin_authentication_required(
    request: Request, _exc: AdminAuthenticationRequired
):
    if request.headers.get("HX-Request") == "true":
        return JSONResponse(
            status_code=401, content={}, headers={"HX-Redirect": "/admin"}
        )
    return RedirectResponse("/admin", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def application_http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request=request,
            name="public/404.html",
            status_code=404,
        )
    return await http_exception_handler(request, exc)


@app.exception_handler(AppException)
async def app_exception_handler(
    request: Request,
    exc: AppException,
):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(AccessAuthenticationRequired)
async def access_authentication_required(
    request: Request, exc: AccessAuthenticationRequired
):
    response = (
        JSONResponse(status_code=401, content={}, headers={"HX-Redirect": exc.location})
        if request.headers.get("HX-Request") == "true"
        else RedirectResponse(exc.location, status_code=303)
    )
    clear_access_cookies(response, device=exc.layer == "device")
    if exc.layer == "device":
        request.state.clear_device_cookie = True
    return response
