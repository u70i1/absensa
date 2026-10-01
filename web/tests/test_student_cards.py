"""Card design, global settings, authorization, scopes, and export lifecycle."""

import base64
import re
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from app.core.config import settings
from app.models.student import Student
from app.models.student_card import StudentCardSettings
from app.schemas.student import StudentListQuery
from app.schemas.student_card import CardSettings, CardSettingsUpdate
from app.services import student_card_service as cards
from app.services import student_card_settings_service as configuration
from app.services.exceptions import AppException
from app.services.student_card_scope_service import resolve_students
from app.services.student_dashboard_service import dashboard_context
from PIL import Image
from pydantic import ValidationError


@pytest.fixture
def sample():
    return SimpleNamespace(
        id=1, name="Abiansyah Viadi", nisn="0081234567", photo_path=None
    )


def test_fixed_dimensions_and_editable_settings():
    config = CardSettings()
    assert (config.width_mm, config.height_mm, config.gap_mm) == (
        Decimal("85.6"),
        Decimal("53.98"),
        3,
    )
    assert set(CardSettings.model_fields) == {"gap_mm", "school_name", "logo_path"}
    assert not config.watermark_enabled
    # Retired settings cannot override the fixed design, including stale clients.
    config = CardSettingsUpdate(
        width_mm=100, height_mm=200, photo_ratio_width=1, photo_ratio_height=1
    )
    assert (config.width_mm, config.height_mm) == (Decimal("85.6"), Decimal("53.98"))


@pytest.mark.parametrize(
    "data",
    [
        {"gap_mm": -1},
        {"gap_mm": 201},
        {"gap_mm": "NaN"},
        {"gap_mm": "Infinity"},
        {"gap_mm": "3.0001"},
        {"school_name": "x" * 161},
    ],
)
def test_invalid_settings(data):
    with pytest.raises(ValidationError):
        CardSettingsUpdate.model_validate(data)


def test_gap_limits(card_admin, db_session):
    for gap in (0, 200, "3.125"):
        response = card_admin.post("/admin/cards/settings", data={"gap_mm": gap})
        assert response.status_code == 200
        assert configuration.get_settings(db_session).gap_mm == Decimal(str(gap))
    for gap in (-1, 201):
        assert (
            card_admin.post("/admin/cards/settings", data={"gap_mm": gap}).status_code
            == 422
        )
        assert configuration.get_settings(db_session).gap_mm == Decimal("3.125")


def test_fixed_card_migration_preserves_gap_and_watermark(db_session, monkeypatch):
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect, text

    migration = (
        ScriptDirectory.from_config(Config("alembic.ini"))
        .get_revision("c64e308f7a12")
        .module
    )
    monkeypatch.setattr(
        migration, "op", Operations(MigrationContext.configure(db_session.connection()))
    )
    config = db_session.get(StudentCardSettings, 1)
    config.gap_mm, config.school_name, config.logo_path, config.watermark_enabled = (
        Decimal("7.5"),
        "Retained School",
        "logo.jpg",
        True,
    )
    db_session.flush()
    migration.downgrade()
    db_session.execute(
        text(
            "UPDATE student_card_settings SET width_mm = 125, height_mm = 200, photo_ratio_width = 4, photo_ratio_height = 5"
        )
    )
    migration.upgrade()
    db_session.expire_all()
    saved = db_session.get(StudentCardSettings, 1)
    assert (
        saved.gap_mm,
        saved.school_name,
        saved.logo_path,
        saved.watermark_enabled,
    ) == (Decimal("7.5"), "Retained School", "logo.jpg", True)
    columns = {
        column["name"]
        for column in inspect(db_session.connection()).get_columns(
            "student_card_settings"
        )
    }
    assert columns == {"id", "gap_mm", "school_name", "logo_path", "watermark_enabled"}


def test_unsaved_settings_preview_uses_placeholder_without_persisting(
    card_admin, db_session, monkeypatch
):
    saved = configuration.get_settings(db_session)
    paths = []
    actual = cards._image_data

    def record(path, **kwargs):
        paths.append(path)
        return actual(path, **kwargs)

    monkeypatch.setattr(cards, "_image_data", record)
    image = BytesIO()
    Image.new("RGB", (50, 50), "blue").save(image, format="PNG")
    response = card_admin.post(
        "/admin/cards/settings/preview",
        data={
            "gap_mm": "35",
            "school_name": "Sekolah Contoh",
            "width_mm": "100",
            "photo_ratio_width": "1",
        },
        files={"logo": ("logo.png", image.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    preview = response.json()
    assert (preview["width_mm"], preview["height_mm"], preview["gap_mm"]) == (
        85.6,
        53.98,
        35,
    )
    svg = base64.b64decode(preview["uri"].split(",")[1]).decode()
    assert "Nama Siswa" in svg and "Sekolah Contoh" in svg
    assert 'data-watermark="true"' in svg
    assert cards.FALLBACK_PHOTO in paths
    photo = ElementTree.fromstring(svg).find(
        "{http://www.w3.org/2000/svg}image[@clip-path]"
    )
    assert float(photo.attrib["width"]) / float(
        photo.attrib["height"]
    ) == pytest.approx(3 / 4)
    db_session.expire_all()
    assert configuration.get_settings(db_session) == saved
    assert not list(configuration.photos.photo_file("logo.jpg").parent.glob("*"))
    assert (
        card_admin.post(
            "/admin/cards/settings/preview", data={"gap_mm": "201"}
        ).status_code
        == 422
    )
    assert (
        card_admin.post(
            "/admin/cards/settings/preview",
            files={"logo": ("bad.png", b"not an image", "image/png")},
        ).status_code
        == 415
    )


def test_renderer_is_auth_independent_and_fallback(sample, monkeypatch):
    actual = cards._image_data
    paths = []

    def record(path, **kwargs):
        paths.append(path)
        return actual(path, **kwargs)

    monkeypatch.setattr(cards, "_image_data", record)
    svg = cards.render_student_card(sample, CardSettings())
    assert cards.FALLBACK_PHOTO in paths
    assert 'viewBox="0 0 856 539.8"' in svg
    assert 'data-barcode="0081234567"' in svg
    assert "Kartu Presensi Absensa" in svg
    assert "http://" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "data-watermark" not in svg
    for path in ("missing.jpg", "../outside.png"):
        sample.photo_path = path
        assert cards.render_student_card(sample, CardSettings()) == svg


def test_png_resolution_physical_size_and_filename(sample):
    png = cards.render_student_card_png(sample, CardSettings())
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1012, 638)
        assert image.width > image.height
        assert all(dpi >= 300 for dpi in image.info["dpi"])
        assert image.width / image.info["dpi"][0] * 25.4 == pytest.approx(
            85.6, abs=0.01
        )
        assert image.height / image.info["dpi"][1] * 25.4 == pytest.approx(
            53.98, abs=0.01
        )
    assert cards.card_filename(sample) == "0081234567-abiansyah-viadi.png"
    sample.name = '../../Asdrölf <script> / "Fickner"'
    assert cards.card_filename(sample) == "0081234567-asdrolf-script-fickner.png"


@pytest.mark.parametrize("has_photo", [False, True])
def test_fixed_photo_ratio_and_center_crop(sample, tmp_path, monkeypatch, has_photo):
    monkeypatch.setattr(settings, "photos_dir", str(tmp_path))
    if has_photo:
        image = Image.new("RGB", (1200, 600), "blue")
        image.paste("red", (0, 0, 200, 600))
        image.paste("green", (1000, 0, 1200, 600))
        image.save(tmp_path / "portrait.png")
        sample.photo_path = "portrait.png"
    root = ElementTree.fromstring(cards.render_student_card(sample, CardSettings()))
    ns = {"s": "http://www.w3.org/2000/svg"}
    photo = root.find("s:image[@clip-path]", ns)
    clip = root.find("s:defs/s:clipPath/s:rect", ns)
    bounds = {key: float(photo.attrib[key]) for key in ("x", "y", "width", "height")}
    assert bounds == pytest.approx({"x": 48, "y": 111, "width": 285.6, "height": 380.8})
    assert bounds["width"] / bounds["height"] == pytest.approx(3 / 4)
    assert all(clip.attrib[key] == photo.attrib[key] for key in bounds)
    with Image.open(
        BytesIO(base64.b64decode(photo.attrib["href"].split(",")[1]))
    ) as cropped:
        assert cropped.size == (768, 1024)
        if has_photo:
            r, g, b = cropped.getpixel((8, cropped.height // 2))
            assert b > 240 and r < 10 and g < 10


@pytest.mark.parametrize("has_photo", [False, True])
def test_barcode_can_be_decoded(sample, tmp_path, monkeypatch, has_photo):
    zxingcpp = pytest.importorskip("zxingcpp")
    if has_photo:
        monkeypatch.setattr(settings, "photos_dir", str(tmp_path))
        Image.new("RGB", (600, 800), "blue").save(tmp_path / "portrait.png")
        sample.photo_path = "portrait.png"
    with Image.open(
        BytesIO(cards.render_student_card_png(sample, CardSettings()))
    ) as image:
        result = zxingcpp.read_barcode(image)
    assert result is not None
    assert result.text == sample.nisn


def test_landscape_details_and_long_name_do_not_overlap_photo_or_barcode(sample):
    sample.name = "Abiansyah Viadi Muhammad Pratama Kusuma Wijaya"
    root = ElementTree.fromstring(cards.render_student_card(sample, CardSettings()))
    ns = {"s": "http://www.w3.org/2000/svg"}
    lines = cards._name_lines(sample.name)
    assert len(lines) == 2
    for line, baseline in lines:
        group = next(
            group
            for group in root.findall("s:g", ns)
            if group.attrib.get("aria-label") == line
        )
        x, y = map(
            float,
            group.attrib["transform"]
            .removeprefix("translate(")
            .removesuffix(")")
            .split(","),
        )
        assert x == pytest.approx(365.6)
        assert y == baseline
        assert y < cards.BARCODE_Y - 36
    nisn = root.find("s:g[@aria-label='NISN ']", ns)
    assert nisn.attrib["transform"].endswith(",227)")


def test_watermark_matches_landscape_header(sample, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "photos_dir", str(tmp_path))
    Image.new("RGB", (100, 50), "blue").save(tmp_path / "logo.png")
    config = CardSettings(school_name="Sekolah <Indah>", logo_path="logo.png")
    svg = cards.render_student_card(sample, config)
    root = ElementTree.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    watermark = root.find("s:g[@data-watermark='true']", ns)
    logo = watermark.find("s:image", ns)
    assert logo.attrib["x"] == "48" and logo.attrib["y"] == "53.5"
    assert logo.attrib["width"] == logo.attrib["height"] == "20"
    assert watermark.attrib["opacity"] == "0.7"
    assert watermark.find("s:g", ns).attrib["transform"] == "translate(76,70.5)"
    assert "Sekolah &lt;Indah&gt;" in svg
    assert svg.count("data:image/jpeg") == 2
    for disabled_config in [
        config.model_copy(update={"logo_path": "missing.png"}),
        config.model_copy(update={"school_name": "", "logo_path": None}),
    ]:
        disabled = cards.render_student_card(sample, disabled_config)
        assert "data-watermark" not in disabled
        assert disabled.count("data:image/jpeg") == 1
        assert "Kartu Presensi Absensa" in disabled


def test_card_background_and_barcode_geometry(sample):
    root = ElementTree.fromstring(cards.render_student_card(sample, CardSettings()))
    ns = {"s": "http://www.w3.org/2000/svg"}
    bars = root.find("s:g[@data-barcode]", ns).findall("s:rect", ns)
    left = float(bars[0].attrib["x"])
    right = float(bars[-1].attrib["x"]) + float(bars[-1].attrib["width"])
    assert left == pytest.approx(365.6)
    assert right == pytest.approx(808)
    assert float(bars[0].attrib["y"]) == pytest.approx(395.8)
    assert float(bars[0].attrib["height"]) == 72
    with Image.open(
        BytesIO(cards.render_student_card_png(sample, CardSettings()))
    ) as image:
        assert image.convert("RGB").getpixel((image.width // 2, 20)) == (244, 251, 249)


def test_watermark_requires_both_fields_and_preserves_saved_logo(
    card_admin, db_session
):
    from app.services.student_photo_service import photo_file

    image = BytesIO()
    Image.new("RGB", (40, 40), "blue").save(image, format="PNG")
    upload = {"logo": ("logo.png", image.getvalue(), "image/png")}
    for data, files in [
        ({"school_name": "Sekolah"}, None),
        ({"school_name": "   "}, upload),
    ]:
        response = card_admin.post("/admin/cards/settings", data=data, files=files)
        assert response.status_code == 422
        assert "bersama-sama" in response.text
        assert configuration.get_settings(db_session).school_name == ""
    assert (
        card_admin.post(
            "/admin/cards/settings", data={"school_name": " Sekolah "}, files=upload
        ).status_code
        == 200
    )
    saved = configuration.get_settings(db_session)
    assert saved.school_name == "Sekolah" and saved.watermark_enabled
    original = saved.logo_path
    for data in [
        {"school_name": ""},
        {"school_name": "Sekolah", "remove_logo": "true"},
    ]:
        response = card_admin.post("/admin/cards/settings", data=data)
        assert response.status_code == 422
        assert configuration.get_settings(db_session).logo_path == original
        assert photo_file(original).is_file()
        assert "Logo sekolah" in response.text
    # Updating a name retains the saved logo; the old toggle is ignored.
    assert (
        card_admin.post(
            "/admin/cards/settings",
            data={"school_name": "Sekolah Baru", "watermark_enabled": "false"},
        ).status_code
        == 200
    )
    assert configuration.get_settings(db_session).watermark_enabled
    assert (
        card_admin.post(
            "/admin/cards/settings", data={"school_name": "", "remove_logo": "true"}
        ).status_code
        == 200
    )
    assert not configuration.get_settings(db_session).watermark_enabled
    assert not photo_file(original).exists()


def test_zip_and_failure_cleanup(sample, monkeypatch):
    second = SimpleNamespace(id=2, name=sample.name, nisn="0081234568", photo_path=None)
    with (
        cards.create_student_card_zip(
            iter([sample, second]), CardSettings()
        ) as archive,
        ZipFile(archive) as zipped,
    ):
        assert zipped.namelist() == [
            cards.card_filename(sample),
            cards.card_filename(second),
        ]
        assert zipped.read(cards.card_filename(sample)).startswith(b"\x89PNG")
    temporary = cards.TemporaryFile()
    monkeypatch.setattr(cards, "TemporaryFile", lambda **kwargs: temporary)

    def fail(*args):
        raise RuntimeError("simulated PNG error")

    monkeypatch.setattr(cards, "render_student_card_png", fail)
    with pytest.raises(AppException, match="Arsip kartu gagal"):
        cards.create_student_card_zip([sample], CardSettings())
    assert temporary.closed


@pytest.mark.parametrize(
    "method,path,data",
    [
        ("get", "/admin/cards", None),
        ("get", "/admin/cards/settings", None),
        ("get", "/admin/cards/settings/logo", None),
        ("get", "/admin/cards/1/preview", None),
        ("post", "/admin/cards/settings", {"width_mm": 80}),
        ("post", "/admin/cards/settings/preview", {"width_mm": 80}),
        (
            "post",
            "/admin/cards/operate",
            {"scope": "all", "action": "print", "confirmed": "true"},
        ),
        (
            "post",
            "/admin/cards/operate",
            {"scope": "selected", "action": "download", "ids": "1"},
        ),
    ],
)
def test_admin_required(client, method, path, data):
    kwargs = {"data": data} if data is not None else {}
    response = getattr(client, method)(path, headers={"HX-Request": "true"}, **kwargs)
    assert response.status_code == 401


def test_settings_persist_and_validate_logo(card_admin, db_session):
    assert configuration.get_settings(db_session) == CardSettings()
    response = card_admin.post(
        "/admin/cards/settings", data={"gap_mm": 4, "width_mm": 80, "height_mm": 1}
    )
    assert response.status_code == 200
    saved = configuration.get_settings(db_session)
    assert (saved.width_mm, saved.height_mm, saved.gap_mm) == (
        Decimal("85.6"),
        Decimal("53.98"),
        4,
    )
    bad = card_admin.post("/admin/cards/settings", data={"gap_mm": -1})
    assert bad.status_code == 422
    assert configuration.get_settings(db_session) == saved
    bad_logo = card_admin.post(
        "/admin/cards/settings",
        files={"logo": ("logo.svg", b"<svg/>", "image/svg+xml")},
    )
    assert bad_logo.status_code == 415
    image = BytesIO()
    Image.new("RGB", (50, 50), "blue").save(image, format="PNG")
    uploaded = card_admin.post(
        "/admin/cards/settings",
        data={"school_name": "Sekolah"},
        files={"logo": ("../../logo.png", image.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 200
    stored = configuration.get_settings(db_session).logo_path
    from app.services.student_photo_service import photo_file

    assert photo_file(stored).is_file()
    assert configuration.get_settings(db_session).watermark_enabled
    assert card_admin.get("/admin/cards/settings/logo").status_code == 200
    card_admin.post("/admin/cards/settings", data={"remove_logo": "true"})
    assert configuration.get_settings(db_session).logo_path is None
    assert not photo_file(stored).exists()


@pytest.mark.parametrize("value", [-1, 201])
def test_settings_database_gap_constraint(db_session, value):
    from sqlalchemy.exc import IntegrityError

    config = db_session.get(StudentCardSettings, 1)
    config.gap_mm = value
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_fixed_settings_apply_to_preview_print_and_download(
    card_admin, db_session, existing_student
):
    assert (
        card_admin.post(
            "/admin/cards/settings",
            data={"gap_mm": "5", "photo_ratio_width": "1", "photo_ratio_height": "1"},
        ).status_code
        == 200
    )
    modal = card_admin.get("/admin/cards/settings")
    for field in (
        "width_mm",
        "height_mm",
        "photo_ratio_width",
        "photo_ratio_height",
        "dimension_source",
    ):
        assert f'name="{field}"' not in modal.text
    saved = configuration.get_settings(db_session)
    preview = card_admin.get(f"/admin/cards/{existing_student.id}/preview")
    printed = card_admin.post(
        "/admin/cards/operate",
        data={"scope": "selected", "ids": existing_student.id, "action": "print"},
    )
    assert "width: 85.6mm; height: 53.98mm" in printed.text
    assert "margin: 0 5.000mm 5.000mm 0" in printed.text
    for response in [preview, printed]:
        assert response.status_code == 200
        svg = base64.b64decode(
            re.search(r'data:image/svg\+xml;base64,([^" ]+)', response.text)[1]
        )
        assert svg.decode() == cards.render_student_card(existing_student, saved)
        photo = ElementTree.fromstring(svg).find(
            "{http://www.w3.org/2000/svg}image[@clip-path]"
        )
        assert float(photo.attrib["width"]) / float(
            photo.attrib["height"]
        ) == pytest.approx(3 / 4)
    downloaded = card_admin.post(
        "/admin/cards/operate",
        data={"scope": "selected", "ids": existing_student.id, "action": "download"},
    )
    assert downloaded.content == cards.render_student_card_png(existing_student, saved)


def test_scopes(db_session, class_factory):
    group = class_factory()
    pupils = [
        Student(
            name=f"Match {i:03d}",
            nisn=f"{i:010d}",
            class_id=group.class_id,
            current=True,
        )
        for i in range(55)
    ]
    outsider = Student(name="Other", nisn="9999999999", current=False)
    db_session.add_all([*pupils, outsider])
    db_session.commit()
    query = StudentListQuery(q="Match", class_id=group.class_id, page=2, limit=50)
    page = dashboard_context(db_session, query)["students"]
    assert len(page) == 5
    selected = resolve_students(
        db_session, "page", [], query, page_ids=[s.id for s in page]
    )
    assert {s.id for s in selected} == {s.id for s in pupils[50:]}
    assert [
        s.id for s in resolve_students(db_session, "selected", [outsider.id], query)
    ] == [outsider.id]
    assert (
        len(list(resolve_students(db_session, "all", [], query, confirmed=True))) == 56
    )
    with pytest.raises(AppException, match="Konfirmasi"):
        resolve_students(db_session, "all", [], query)
    with pytest.raises(AppException, match="berubah"):
        resolve_students(db_session, "page", [], query, page_ids=[outsider.id])
    for ids in ([], [2147483647], ["bad"], [-1], [999999999999999999999999999999]):
        with pytest.raises(AppException):
            resolve_students(db_session, "selected", ids, query)


def test_print_and_download_routes(card_admin, existing_student, student_factory):
    page = card_admin.get("/admin/cards")
    assert page.status_code == 200
    assert "data-card-operation" in page.text
    assert 'action="http://testserver/admin/cards"' in page.text
    assert "data-selection-toggle" in page.text
    assert "admin_card" not in page.text  # Jinja resolved route names.
    fragment = card_admin.get("/admin/cards?q=Nicholas", headers={"HX-Request": "true"})
    assert fragment.headers["HX-Push-Url"].startswith("/admin/cards?")
    assert "<html" not in fragment.text
    payload = {"scope": "page", "page_ids": str(existing_student.id), "action": "print"}
    printed = card_admin.post("/admin/cards/operate", data=payload)
    assert printed.status_code == 200
    assert "break-inside: avoid" in printed.text
    assert "page-break-inside: avoid" in printed.text
    assert "window.print()" in printed.text
    assert "top-header" not in printed.text
    assert printed.text.count('<article class="student-card">') == 1
    payload = {
        "scope": "selected",
        "ids": str(existing_student.id),
        "action": "download",
    }
    png = card_admin.post("/admin/cards/operate", data=payload)
    assert png.headers["content-type"] == "image/png"
    assert cards.card_filename(existing_student) in png.headers["content-disposition"]
    student_factory(nisn="0081234567", name="Other")
    all_payload = {"scope": "all", "action": "download", "confirmed": "true"}
    archive = card_admin.post("/admin/cards/operate?q=NoMatch&page=8", data=all_payload)
    assert archive.headers["content-type"] == "application/zip"
    assert re.search(
        r"student-cards-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.zip",
        archive.headers["content-disposition"],
    )
    with ZipFile(BytesIO(archive.content)) as zipped:
        assert len(zipped.namelist()) == 2
    preview = card_admin.get(f"/admin/cards/{existing_student.id}/preview")
    assert preview.status_code == 200
    svg = base64.b64decode(
        re.search(r'data:image/svg\+xml;base64,([^" ]+)', preview.text)[1]
    )
    assert existing_student.nisn.encode() in svg


def test_empty_and_unconfirmed_operations(card_admin):
    for data in (
        {"scope": "selected", "action": "print"},
        {"scope": "page", "action": "download"},
        {"scope": "all", "action": "print"},
        {"scope": "all", "action": "download", "confirmed": "true"},
    ):
        assert card_admin.post("/admin/cards/operate", data=data).status_code == 422


def test_generation_failures_are_presented(card_admin, existing_student, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("full disk")

    monkeypatch.setattr(cards.cairosvg, "svg2png", fail)
    response = card_admin.post(
        "/admin/cards/operate",
        data={"scope": "selected", "action": "download", "ids": existing_student.id},
    )
    assert response.status_code == 500
    assert "Gambar kartu gagal" in response.text
