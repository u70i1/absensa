"""Administrator attendance log, single-day filtering, and spreadsheet export."""

from datetime import date, datetime, timedelta
from math import ceil
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.routes.admin import Db, render_modal
from app.schemas.scan import AdminScanQuery
from app.services import export_service, scan_service
from app.templating import templates
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

router = APIRouter(
    prefix="/admin/scans",
    default_response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
PAGE_SIZE = 50
LOCAL_TZ = ZoneInfo(settings.timezone)


def scan_query(request: Request) -> AdminScanQuery:
    values = dict(request.query_params)
    if not values.get("day"):
        values["day"] = datetime.now(LOCAL_TZ).date().isoformat()
    values["q"] = values.get("q", "").strip()
    values["limit"] = PAGE_SIZE
    return AdminScanQuery.model_validate(values)


def list_url(query: AdminScanQuery, **changes) -> str:
    values = {"day": query.day.isoformat(), "q": query.q, "page": query.page} | changes
    values = {key: value for key, value in values.items() if value not in (None, "")}
    return f"/admin/scans?{urlencode(values)}"


def invalid_filters(request: Request):
    return render_modal(
        request,
        "modals/message.html",
        {
            "title": "Filter tidak valid",
            "error": "Periksa tanggal, nama, dan nomor halaman pada alamat halaman.",
            "back_url": "/admin/scans",
            "back_label": "Kembali ke log presensi",
        },
        422,
    )


def render_directory(request: Request, db: Db, query: AdminScanQuery, message=None):
    total = scan_service.count_admin_scans(db, query.day, query.q)
    pages = max(1, ceil(total / PAGE_SIZE))
    if query.page > pages:
        query = query.model_copy(update={"page": 1})
    scans = scan_service.get_admin_scans(
        db, query.day, query.q, page=query.page, limit=PAGE_SIZE
    )
    page_numbers = sorted(
        {1, pages, *range(max(1, query.page - 2), min(pages, query.page + 2) + 1)}
    )
    fragment = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )
    response = templates.TemplateResponse(
        request=request,
        name="tables/scan-results.html" if fragment else "admin/pages/scans.html",
        context={
            "query": query,
            "scans": scans,
            "total": total,
            "pages": pages,
            "page_numbers": page_numbers,
            "start": (query.page - 1) * PAGE_SIZE + 1 if total else 0,
            "end": min(query.page * PAGE_SIZE, total),
            "message": message,
            "scan_timezone": LOCAL_TZ,
            "list_url": lambda **changes: list_url(query, **changes),
            "previous_day": query.day - timedelta(days=1)
            if query.day > date.min
            else None,
            "next_day": query.day + timedelta(days=1)
            if query.day < date.max - timedelta(days=1)
            else None,
        },
    )
    response.headers["Vary"] = "HX-Request, HX-History-Restore-Request"
    if fragment:
        response.headers["HX-Push-Url"] = list_url(query)
    return response


def mutation_response(request: Request, db: Db, query: AdminScanQuery, message: str):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(list_url(query), status_code=303)
    response = render_directory(request, db, query, message)
    response.headers.update(
        {
            "HX-Retarget": "#scan-results",
            "HX-Reswap": "outerHTML",
            "HX-Trigger-After-Swap": "scanSaved",
        }
    )
    return response


@router.get("", name="admin_scans")
def scans(request: Request, db: Db):
    try:
        query = scan_query(request)
    except ValidationError:
        return invalid_filters(request)
    return render_directory(request, db, query)


@router.get("/export", name="admin_scans_export")
def export_scans(request: Request, db: Db):
    try:
        query = scan_query(request)
    except ValidationError:
        return invalid_filters(request)
    scans = scan_service.get_admin_scans(db, query.day, query.q)
    summary = query.day.strftime("%d/%m/%Y")
    if query.q:
        summary += f' · Nama "{query.q}"'
    content = export_service.build_scans_workbook(scans, summary)
    filename = f"ekspor-log-presensi-{query.day.isoformat()}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
