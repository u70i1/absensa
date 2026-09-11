from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin")

BASE_DIR = Path(__file__).resolve().parents[1]  # backend/ folder
templates = Jinja2Templates(directory=BASE_DIR / "templates")
router.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
