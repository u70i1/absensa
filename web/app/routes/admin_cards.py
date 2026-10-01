"""Administrator boundaries for the reusable student card tools."""

import logging
from datetime import datetime
from itertools import chain, islice
from tempfile import TemporaryFile
from threading import BoundedSemaphore
from typing import Annotated
from zoneinfo import ZoneInfo

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.routes.admin import list_query, query_error, render_modal
from app.schemas.student import StudentListQuery
from app.schemas.student_card import CardSettingsUpdate
from app.services import student_card_service as cards
from app.services import student_card_settings_service as configuration
from app.services.exceptions import AppException
from app.services.student_card_scope_service import resolve_students
from app.services.student_dashboard_service import dashboard_context
from app.services.student_photo_service import photo_file
from app.services.student_service import get_student_by_id
from app.templating import templates
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

router = APIRouter(prefix="/admin/cards", dependencies=[Depends(require_admin)])
Db = Annotated[Session, Depends(get_db)]
logger = logging.getLogger(__name__)
generation_slots = BoundedSemaphore(2)


class TemporaryDocumentResponse(StreamingResponse):
    """Own an anonymous temporary file, including on interrupted transfers."""

    def __init__(self, document, **kwargs):
        self.document = document
        super().__init__(iter(lambda: document.read(64 * 1024), b""), **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.document.close()


def card_error(request, exc):
    return render_modal(
        request,
        "modals/message.html",
        {
            "title": "Kartu belum dapat dibuat",
            "error": exc.detail,
        },
        exc.status_code,
    )


@router.get("", name="admin_cards", response_class=HTMLResponse)
def card_page(request: Request, db: Db):
    try:
        context = dashboard_context(db, list_query(request), base_url="/admin/cards")
    except ValidationError:
        return query_error(request)
    fragment = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )
    context |= {"card_mode": True, "list_route": "admin_cards"}
    response = templates.TemplateResponse(
        request=request,
        name="tables/student-results.html" if fragment else "admin/pages/cards.html",
        context=context,
    )
    response.headers["Vary"] = "HX-Request, HX-History-Restore-Request"
    if fragment:
        response.headers["HX-Push-Url"] = context["list_url"]()
    return response


@router.get("/settings", name="admin_card_settings")
def settings_modal(request: Request, db: Db):
    return render_modal(
        request, "modals/card-settings.html", {"values": configuration.get_settings(db)}
    )


@router.get("/settings/logo", name="admin_card_logo")
def school_logo(db: Db):
    config = configuration.get_settings(db)
    if not config.logo_path:
        raise AppException("Logo sekolah tidak ditemukan.", 404)
    return FileResponse(
        photo_file(config.logo_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )


def settings_error_values(db, data):
    values = configuration.get_settings(db).model_dump()
    values.update(
        {
            key: data[key]
            for key in (
                "width_mm",
                "height_mm",
                "gap_mm",
                "photo_ratio_width",
                "photo_ratio_height",
                "school_name",
                "dimension_source",
                "remove_logo",
            )
            if key in data
        }
    )
    return values


async def card_form(request: Request):
    async with request.form() as form:
        yield form


@router.post("/settings", name="admin_card_settings_save")
def save_settings(
    request: Request, db: Db, data: Annotated[FormData, Depends(card_form)]
):
    try:
        values = CardSettingsUpdate.model_validate(
            {
                key: data.get(key, default)
                for key, default in {
                    "width_mm": "70",
                    "height_mm": "112",
                    "gap_mm": "3",
                    "photo_ratio_width": "3",
                    "photo_ratio_height": "4",
                    "school_name": "",
                    "dimension_source": "width",
                }.items()
            }
        )
        logo = data.get("logo")
        configuration.update_settings(
            db,
            values,
            logo.file if getattr(logo, "filename", "") else None,
            remove_logo=data.get("remove_logo") == "true",
        )
    except (ValidationError, ArithmeticError, AppException) as exc:
        message = (
            exc.detail
            if isinstance(exc, AppException)
            else "Periksa ukuran kartu (lebar 40–150 mm, rasio 5:8), jarak 0–20 mm, rasio foto berupa angka positif (boleh desimal), dan nama sekolah maksimal 160 karakter."
        )
        return render_modal(
            request,
            "modals/card-settings.html",
            {
                "values": settings_error_values(db, data),
                "error": message,
            },
            exc.status_code if isinstance(exc, AppException) else 422,
        )
    except Exception:
        logger.exception("Could not save card settings")
        return render_modal(
            request,
            "modals/card-settings.html",
            {
                "values": settings_error_values(db, data),
                "error": "Pengaturan gagal disimpan. Silakan coba lagi.",
            },
            500,
        )
    return render_modal(
        request,
        "modals/card-settings.html",
        {
            "values": configuration.get_settings(db),
            "message": "Pengaturan cetak berhasil disimpan untuk semua kartu.",
        },
    )


@router.get("/{student_id:int}/preview", name="admin_card_preview")
def preview(student_id: int, request: Request, db: Db):
    try:
        student = get_student_by_id(db, student_id)
        config = configuration.get_settings(db)
        card = next(cards.prepare_student_cards_for_print([student], config))
        return render_modal(
            request,
            "modals/card-preview.html",
            {"student": student, "card": card, "config": config},
        )
    except AppException as exc:
        return card_error(request, exc)


def print_document(students, config):
    document = TemporaryFile(mode="w+b")  # noqa: SIM115 — response owns file lifetime
    try:
        template = templates.env.get_template("cards/print.html")
        for part in template.generate(
            cards=cards.prepare_student_cards_for_print(students, config), config=config
        ):
            document.write(part.encode("utf-8"))
        document.seek(0)
        return TemporaryDocumentResponse(document, media_type="text/html")
    except Exception:
        document.close()
        raise


def download_document(students, config):
    students = iter(students)
    first = list(islice(students, 2))
    if not first:
        raise AppException("Tidak ada siswa untuk dibuatkan kartu.", 422)
    if len(first) == 1:
        return Response(
            cards.render_student_card_png(first[0], config),
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{cards.card_filename(first[0])}"'
            },
        )
    archive = cards.create_student_card_zip(chain(first, students), config)
    filename = datetime.now(ZoneInfo(settings.timezone)).strftime(
        "student-cards-%Y-%m-%d_%H-%M-%S.zip"
    )
    return TemporaryDocumentResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/operate", name="admin_card_operation")
def operate(request: Request, db: Db, data: Annotated[FormData, Depends(card_form)]):
    if not generation_slots.acquire(blocking=False):
        return card_error(
            request,
            AppException(
                "Server sedang membuat kartu. Tunggu hingga proses selesai, lalu coba lagi.",
                503,
            ),
        )
    try:
        action = data.get("action")
        if action not in {"print", "download"}:
            raise AppException("Tindakan kartu tidak valid.", 422)
        students = iter(
            resolve_students(
                db,
                data.get("scope"),
                data.getlist("ids"),
                list_query(request)
                if data.get("scope") == "page"
                else StudentListQuery(),
                confirmed=data.get("confirmed") == "true",
                page_ids=data.getlist("page_ids"),
            )
        )
        first = next(students, None)
        if first is None:
            raise AppException("Tidak ada siswa untuk dibuatkan kartu.", 422)
        students = chain([first], students)
        config = configuration.get_settings(db)
        return (
            print_document(students, config)
            if action == "print"
            else download_document(students, config)
        )
    except ValidationError:
        return query_error(request)
    except AppException as exc:
        return card_error(request, exc)
    except Exception:
        logger.exception("Card operation failed")
        return card_error(
            request, AppException("Kartu gagal dibuat. Silakan coba lagi.", 500)
        )
    finally:
        generation_slots.release()
