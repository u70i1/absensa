"""Device and operator management inside the existing administrator dashboard."""

from typing import Literal

from app.core.admin_auth import CurrentAdmin, require_admin
from app.routes.admin import Db, form_data, render_modal
from app.services import access_management_service as management
from app.services.exceptions import AppException
from app.templating import templates
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/admin/access", dependencies=[Depends(require_admin)])
Kind = Literal["devices", "operators"]


def directory_response(request, db, message=None):
    fragment = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )
    response = templates.TemplateResponse(
        request=request,
        name="tables/access-results.html" if fragment else "admin/pages/access.html",
        context={
            "devices": management.directory(db, "devices"),
            "operators": management.directory(db, "operators"),
            "message": message,
        },
    )
    response.headers["Vary"] = "HX-Request, HX-History-Restore-Request"
    return response


def modal_response(request, template, context, status_code=200):
    return render_modal(
        request,
        template,
        context
        | {
            "back_url": "/admin/access",
            "back_label": "Kembali ke akses & perangkat",
            "dialog_title": "Akses & Perangkat",
        },
        status_code,
    )


def form_response(request, kind, item=None, values=None, error=None, status_code=200):
    return modal_response(
        request,
        "modals/access-form.html",
        {
            "kind": kind,
            "item": management.public_account(item) if item else None,
            "values": values
            if values is not None
            else (management.public_account(item) if item else {"active": True}),
            "error": error,
        },
        status_code,
    )


def error_response(request, exc):
    return modal_response(
        request,
        "modals/message.html",
        {"title": "Permintaan tidak dapat diproses", "error": exc.detail},
        exc.status_code,
    )


def saved(request, db, message):
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/admin/access", status_code=303)
    response = directory_response(request, db, message)
    response.headers.update(
        {
            "HX-Retarget": "#access-results",
            "HX-Reswap": "outerHTML",
            "HX-Trigger-After-Swap": "accessSaved",
        }
    )
    return response


@router.get("", name="admin_access")
def directory(request: Request, db: Db):
    return directory_response(request, db)


@router.get("/{kind}/new", name="admin_access_new")
def new_account(request: Request, kind: Kind):
    return form_response(request, kind)


@router.get("/{kind}/{account_id:int}/edit", name="admin_access_edit")
def edit_account(request: Request, kind: Kind, account_id: int, db: Db):
    try:
        return form_response(request, kind, management.account(db, kind, account_id))
    except AppException as exc:
        return error_response(request, exc)


def save(request, db, admin, kind, data, account_id=None):
    try:
        management.save_account(db, kind, admin.id, data, account_id)
    except AppException as exc:
        db.rollback()
        try:
            item = (
                management.account(db, kind, account_id)
                if account_id is not None
                else None
            )
        except AppException:
            return error_response(request, exc)
        # Secrets never enter the template context, including on validation errors.
        return form_response(
            request,
            kind,
            item,
            {
                "name": str(data.get("name", ""))[:100],
                "active": data.get("active") == "true",
            },
            exc.detail,
            exc.status_code,
        )
    return saved(request, db, "Akun berhasil disimpan.")


@router.post("/{kind}", name="admin_access_create")
def create_account(
    request: Request,
    kind: Kind,
    db: Db,
    admin: CurrentAdmin,
    data: dict = Depends(form_data),
):
    return save(request, db, admin, kind, data)


@router.post("/{kind}/{account_id:int}/edit", name="admin_access_update")
def update_account(
    request: Request,
    kind: Kind,
    account_id: int,
    db: Db,
    admin: CurrentAdmin,
    data: dict = Depends(form_data),
):
    return save(request, db, admin, kind, data, account_id)


@router.get("/{kind}/{account_id:int}/{action}", name="admin_access_confirmation")
def confirmation(
    request: Request,
    kind: Kind,
    account_id: int,
    action: Literal["revoke", "delete"],
    db: Db,
):
    try:
        item = management.account(db, kind, account_id)
        if action == "revoke" and kind != "devices":
            raise AppException("Tindakan tidak ditemukan.", 404)
        return modal_response(
            request,
            "modals/access-confirm.html",
            {"kind": kind, "item": management.public_account(item), "action": action},
        )
    except AppException as exc:
        return error_response(request, exc)


@router.post("/{kind}/{account_id:int}/{action}", name="admin_access_action")
def account_action(
    request: Request,
    kind: Kind,
    account_id: int,
    action: Literal["revoke", "delete"],
    db: Db,
):
    try:
        management.manage_account(db, kind, account_id, action)
    except AppException as exc:
        db.rollback()
        return error_response(request, exc)
    return saved(
        request,
        db,
        "Koneksi perangkat direset. Akun dapat digunakan untuk masuk kembali."
        if action == "revoke"
        else "Akun dihapus.",
    )
