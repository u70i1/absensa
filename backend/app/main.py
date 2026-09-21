from app.core.admin_auth import AdminAuthenticationRequired
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


# This should direct to login page
@app.get("/")
def root():
    return "Server is running"


app.include_router(api_router)


@app.exception_handler(AdminAuthenticationRequired)
async def admin_authentication_required(
    request: Request, _exc: AdminAuthenticationRequired
):
    if request.headers.get("HX-Request") == "true":
        return JSONResponse(status_code=401, content={}, headers={"HX-Redirect": "/"})
    return RedirectResponse("/", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def application_http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request=request, name="404.html", status_code=404,
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
