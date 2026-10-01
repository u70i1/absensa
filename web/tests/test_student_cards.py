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


def test_defaults_and_ratio():
    config = CardSettings()
    assert (config.width_mm, config.height_mm, config.gap_mm) == (70, 112, 3)
    assert (config.photo_ratio_width, config.photo_ratio_height) == (3, 4)
    assert not config.watermark_enabled
    with pytest.raises(ValidationError):
        CardSettings(width_mm=70, height_mm=100)


@pytest.mark.parametrize(
    "data,width,height",
    [
        ({"width_mm": 80, "height_mm": 112}, 80, 128),
        (
            {"dimension_source": "height", "height_mm": 100, "width_mm": 70},
            Decimal("62.5"),
            100,
        ),
        ({"width_mm": "70.125"}, Decimal("70.125"), Decimal("112.2")),
    ],
)
def test_ratio_synchronization(data, width, height):
    config = CardSettingsUpdate.model_validate(data)
    assert config.width_mm == width
    assert config.height_mm == height


@pytest.mark.parametrize(
    "data",
    [
        {"width_mm": 0},
        {"width_mm": 151},
        {"gap_mm": -1},
        {"gap_mm": 21},
        {"width_mm": "NaN"},
        {"school_name": "x" * 161},
        {"photo_ratio_width": 0},
        {"photo_ratio_height": -4},
        {"photo_ratio_width": "NaN"},
        {"photo_ratio_height": "Infinity"},
        {"photo_ratio_width": "-Infinity"},
        {"photo_ratio_height": ""},
    ],
)
def test_invalid_settings(data):
    with pytest.raises((ValidationError, ArithmeticError)):
        CardSettingsUpdate.model_validate(data)


def test_renderer_is_auth_independent_and_fallback(sample, monkeypatch):
    actual = cards._image_data
    paths = []

    def record(path, **kwargs):
        paths.append(path)
        return actual(path, **kwargs)

    monkeypatch.setattr(cards, "_image_data", record)
    svg = cards.render_student_card(sample, CardSettings())
    assert cards.FALLBACK_PHOTO in paths
    assert str(cards.FALLBACK_PHOTO).endswith("static/images/no-photo.png")
    assert 'viewBox="0 0 800 1280"' in svg
    assert 'data-barcode="0081234567"' in svg
    assert "http://" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "data-watermark" not in svg
    sample.photo_path = "missing.jpg"
    assert cards.render_student_card(sample, CardSettings()) == svg
    sample.photo_path = "../outside.png"
    assert cards.render_student_card(sample, CardSettings()) == svg


def test_png_resolution_and_filename(sample):
    png = cards.render_student_card_png(sample, CardSettings())
    with Image.open(BytesIO(png)) as image:
        assert image.width * 8 == image.height * 5
        assert image.width >= 70 / 25.4 * 300
        assert image.height >= 112 / 25.4 * 300
        assert image.info["dpi"][0] >= 300
    assert cards.card_filename(sample) == "0081234567-abiansyah-viadi.png"
    sample.name = '../../Asdrölf <script> / "Fickner"'
    assert cards.card_filename(sample) == "0081234567-asdrolf-script-fickner.png"


@pytest.mark.parametrize("width,height", [(3, 4), (1, 1), (4, 3), (3.5, 4.5)])
@pytest.mark.parametrize("has_photo", [False, True])
def test_photo_ratio_and_center_crop(
    sample, tmp_path, monkeypatch, width, height, has_photo
):
    monkeypatch.setattr(settings, "photos_dir", str(tmp_path))
    if has_photo:
        # A wide image with colored edges makes a centered portrait crop visible.
        image = Image.new("RGB", (1200, 600), "blue")
        image.paste("red", (0, 0, 200, 600))
        image.paste("green", (1000, 0, 1200, 600))
        image.save(tmp_path / "portrait.png")
        sample.photo_path = "portrait.png"
    config = CardSettings(photo_ratio_width=width, photo_ratio_height=height)
    root = ElementTree.fromstring(cards.render_student_card(sample, config))
    ns = {"s": "http://www.w3.org/2000/svg"}
    photo = root.find("s:image[@clip-path]", ns)
    clip = root.find("s:defs/s:clipPath/s:rect", ns)
    bounds = {key: float(photo.attrib[key]) for key in ("x", "y", "width", "height")}
    assert bounds["width"] / bounds["height"] == pytest.approx(width / height)
    assert max(bounds["width"], bounds["height"]) == 720
    assert bounds["x"] + bounds["width"] / 2 == 400
    assert bounds["y"] + bounds["height"] / 2 == 496
    assert all(clip.attrib[key] == photo.attrib[key] for key in bounds)
    with Image.open(
        BytesIO(base64.b64decode(photo.attrib["href"].split(",")[1]))
    ) as cropped:
        assert cropped.width / cropped.height == pytest.approx(
            width / height, abs=0.002
        )
        if has_photo:
            # Sample just inside the crop, away from JPEG/resampling edges.
            r, g, b = cropped.getpixel((8, cropped.height // 2))
            assert b > 240 and r < 10 and g < 10


def test_barcode_can_be_decoded(sample):
    # Optional independent decoder; not a runtime dependency.
    zxingcpp = pytest.importorskip("zxingcpp")
    png = cards.render_student_card_png(sample, CardSettings())
    with Image.open(BytesIO(png)) as image:
        result = zxingcpp.read_barcode(image)
    assert result is not None
    assert result.text == sample.nisn


def test_watermark(sample, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "photos_dir", str(tmp_path))
    Image.new("RGB", (100, 50), "blue").save(tmp_path / "logo.png")
    config = CardSettings(school_name="Sekolah <Indah>", logo_path="logo.png")
    svg = cards.render_student_card(sample, config)
    assert 'data-watermark="true"' in svg
    assert "Sekolah &lt;Indah&gt;" in svg
    assert svg.count("data:image/jpeg") == 2
    root = ElementTree.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    watermark = root.find("s:g[@data-watermark='true']", ns)
    logo = watermark.find("s:image", ns)
    width = min(cards._text_width(config.school_name, 26, 400), 650)
    assert float(logo.attrib["x"]) + (70 + width) / 2 == pytest.approx(400, abs=0.001)
    text = watermark.find("s:g", ns)
    assert text.attrib["transform"].endswith(",84)")
    missing = cards.render_student_card(
        sample, config.model_copy(update={"logo_path": "missing.png"})
    )
    assert missing.count("data:image/jpeg") == 1
    assert "data-watermark" not in missing
    disabled = cards.render_student_card(
        sample, config.model_copy(update={"school_name": "", "logo_path": None})
    )
    assert "data-watermark" not in disabled
    assert "Sekolah" not in disabled
    assert disabled.count("data:image/jpeg") == 1


def test_white_card_and_barcode_width(sample):
    svg = cards.render_student_card(sample, CardSettings())
    root = ElementTree.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    bars = root.find("s:g[@data-barcode]", ns).findall("s:rect", ns)
    left = float(bars[0].attrib["x"])
    right = float(bars[-1].attrib["x"]) + float(bars[-1].attrib["width"])
    assert left == 40
    assert right - left == pytest.approx(720)
    with Image.open(
        BytesIO(cards.render_student_card_png(sample, CardSettings()))
    ) as image:
        assert image.convert("RGB").getpixel((image.width // 2, 20)) == (255, 255, 255)


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
        "/admin/cards/settings",
        data={
            "width_mm": 80,
            "height_mm": 1,
            "gap_mm": 4,
        },
    )
    assert response.status_code == 200
    saved = configuration.get_settings(db_session)
    assert (saved.width_mm, saved.height_mm, saved.gap_mm) == (80, 128, 4)
    assert not saved.watermark_enabled
    response = card_admin.post(
        "/admin/cards/settings", data={"dimension_source": "height", "height_mm": 100}
    )
    assert response.status_code == 200
    assert configuration.get_settings(db_session).width_mm == Decimal("62.5")
    bad = card_admin.post("/admin/cards/settings", data={"width_mm": -1})
    assert bad.status_code == 422
    assert configuration.get_settings(db_session).width_mm == Decimal("62.5")
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


def test_settings_database_ratio_constraint(db_session):
    from sqlalchemy.exc import IntegrityError

    config = db_session.get(StudentCardSettings, 1)
    config.height_mm = 100
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("field", ["photo_ratio_width", "photo_ratio_height"])
@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_settings_database_photo_ratio_constraint(db_session, field, value):
    from sqlalchemy.exc import IntegrityError

    config = db_session.get(StudentCardSettings, 1)
    setattr(config, field, value)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_photo_ratio_settings_persist_and_apply(
    card_admin, db_session, existing_student
):
    response = card_admin.post(
        "/admin/cards/settings",
        data={"photo_ratio_width": "3.5", "photo_ratio_height": "4.5"},
    )
    assert response.status_code == 200
    db_session.expire_all()
    saved = configuration.get_settings(db_session)
    assert (saved.photo_ratio_width, saved.photo_ratio_height) == (3.5, 4.5)
    modal = card_admin.get("/admin/cards/settings")
    assert 'name="photo_ratio_width"' in modal.text and 'value="3.5"' in modal.text
    preview = card_admin.get(f"/admin/cards/{existing_student.id}/preview")
    printed = card_admin.post(
        "/admin/cards/operate",
        data={"scope": "selected", "ids": existing_student.id, "action": "print"},
    )
    for response in [preview, printed]:
        assert response.status_code == 200
        svg = base64.b64decode(
            re.search(r'data:image/svg\+xml;base64,([^" ]+)', response.text)[1]
        )
        photo = ElementTree.fromstring(svg).find("{http://www.w3.org/2000/svg}image")
        assert float(photo.attrib["width"]) / float(
            photo.attrib["height"]
        ) == pytest.approx(3.5 / 4.5)
    downloaded = card_admin.post(
        "/admin/cards/operate",
        data={"scope": "selected", "ids": existing_student.id, "action": "download"},
    )
    assert downloaded.content == cards.render_student_card_png(existing_student, saved)
    bad = card_admin.post(
        "/admin/cards/settings",
        data={"photo_ratio_width": "3.5", "photo_ratio_height": "0"},
    )
    assert bad.status_code == 422
    assert 'value="3.5"' in bad.text and 'value="0"' in bad.text
    assert configuration.get_settings(db_session) == saved


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
