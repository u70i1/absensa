"""Attendance application built on the existing scan service."""

from typing import Annotated
from zoneinfo import ZoneInfo

from app.core.access_auth import CurrentDevice, CurrentOperator, Db
from app.core.config import settings
from app.services import scan_service
from app.services import student_photo_service
from app.services.exceptions import AppException
from app.templating import templates
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(prefix="/operator")
Before = Annotated[int | None, Query(ge=1)]


def history_context(db, before=None):
    return scan_service.get_recent_history(db, before) | {
        "history_timezone": ZoneInfo(settings.timezone),
        "before": before,
    }


def recent_context(db):
    return scan_service.get_today_history(db) | {
        "history_timezone": ZoneInfo(settings.timezone)
    }


def result_response(
    request, db, operator, device, result=None, error=None, status_code=200, before=None
):
    fragment = request.headers.get("HX-Request") == "true"
    context = {
        "operator_name": operator.display_name,
        "device_name": device.username,
        "result": result,
        "error": error,
        "nisn": "" if result else getattr(request.state, "scan_nisn", ""),
        "is_fragment": fragment,
        "history_timezone": ZoneInfo(settings.timezone),
    }
    if not fragment:
        context.update(recent_context(db))
    response = templates.TemplateResponse(
        request=request,
        name="operator/components/scan-feedback.html"
        if fragment
        else "operator/pages/dashboard.html",
        context=context,
        status_code=status_code,
    )
    if fragment:
        response.headers["X-Operator-Fragment"] = "scan"
    return response


@router.get("/recent", name="operator_recent")
def recent_scans(
    request: Request, db: Db, operator: CurrentOperator, device: CurrentDevice
):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/operator", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="operator/components/recent-scans.html",
        context=recent_context(db),
    )


@router.get("/students/{student_id}/photo", name="operator_student_photo")
def student_photo(
    student_id: int, db: Db, operator: CurrentOperator, device: CurrentDevice
):
    return FileResponse(
        student_photo_service.get_student_photo(db, student_id),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("", name="operator_app")
def operator_app(
    request: Request,
    db: Db,
    operator: CurrentOperator,
    device: CurrentDevice,
    before: Before = None,
):
    return result_response(request, db, operator, device, before=before)


@router.get("/history", name="operator_history")
def operator_history(
    request: Request, db: Db, operator: CurrentOperator, before: Before = None
):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            "/operator" + (f"?before={before}" if before else ""), status_code=303
        )
    return templates.TemplateResponse(
        request=request,
        name="operator/components/history-rows.html",
        context=history_context(db, before),
    )


@router.post("/scans", name="operator_scan")
def scan(
    request: Request,
    db: Db,
    operator: CurrentOperator,
    device: CurrentDevice,
    nisn: Annotated[str, Form()] = "",
):
    request.state.scan_nisn = nisn[:10]
    try:
        if len(nisn) != 10 or not nisn.isascii() or not nisn.isdecimal():
            raise AppException("NISN harus berisi tepat 10 digit.", 422)
        result = scan_service.post_scan(db, nisn)
        return result_response(request, db, operator, device, result)
    except AppException as exc:
        message = {
            "student_not_found": "Siswa aktif tidak ditemukan.",
            "duplicate_scan": "Siswa sudah absen hari ini.",
        }.get(exc.detail, exc.detail)
        return result_response(
            request, db, operator, device, error=message, status_code=exc.status_code
        )
