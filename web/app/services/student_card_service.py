"""Reusable, authorization-neutral card rendering and bounded-memory exports.

All visible card content is generated here as self-contained SVG. Text uses the
bundled Inter font outlines so browser print and Cairo PNG need no system fonts.
Calling routes must authorize access before passing students to these functions.
"""

import base64
import logging
import re
import unicodedata
from functools import lru_cache
from io import BytesIO
from math import ceil
from tempfile import TemporaryFile
from threading import RLock
from xml.sax.saxutils import escape
from zipfile import ZIP_STORED, ZipFile

import cairosvg
from app.schemas.student_card import CardSettings
from app.services.exceptions import AppException
from app.services.student_photo_service import photo_file
from app.templating import APP_DIR
from barcode import Code128
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)
FALLBACK_PHOTO = APP_DIR / "static/images/no-photo.png"
PRINT_DPI = 300
_font_lock = RLock()


@lru_cache(maxsize=2)
def _font(weight):
    font = TTFont(APP_DIR / "static/fonts/InterVariable.woff2")
    return (
        font.getGlyphSet(location={"wght": weight}),
        font.getBestCmap(),
        font["head"].unitsPerEm,
    )


@lru_cache(maxsize=2048)
def _glyph(character, weight):
    # Variable font glyph sets temporarily mutate their drawing location.
    with _font_lock:
        glyphs, cmap, units = _font(weight)
        glyph = glyphs[cmap.get(ord(character), ".notdef")]
        pen = SVGPathPen(glyphs)
        glyph.draw(pen)
        return pen.getCommands(), glyph.width, units


def _text_width(text, size, weight):
    return sum(_glyph(c, weight)[1] / _glyph(c, weight)[2] * size for c in text)


def _text(text, x, y, size, *, weight=400, fill="#192321", max_width=720):
    width = _text_width(text, size, weight)
    size *= min(1, max_width / width) if width else 1
    paths = []
    offset = 0
    for character in text:
        path, advance, units = _glyph(character, weight)
        scale = size / units
        paths.append(
            f'<path transform="translate({offset:.3f}) scale({scale:.6f},-{scale:.6f})" d="{path}"/>'
        )
        offset += advance * scale
    return f'<g aria-label="{escape(text, {chr(34): "&quot;"})}" fill="{fill}" transform="translate({x},{y})">{"".join(paths)}</g>'


def _name_lines(name):
    name = " ".join(name.split())
    if _text_width(name, 48, 700) <= 720:
        return [(name, 950)]
    words = name.split()
    if len(words) == 1:
        return [(name, 950)]
    split = min(
        range(1, len(words)),
        key=lambda i: max(
            _text_width(" ".join(words[:i]), 48, 700),
            _text_width(" ".join(words[i:]), 48, 700),
        ),
    )
    return [(" ".join(words[:split]), 910), (" ".join(words[split:]), 965)]


def _image_data(path, *, square=False):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if square:
            image = ImageOps.fit(image, (1024, 1024), method=Image.Resampling.LANCZOS)
        else:
            image.thumbnail((512, 512))
        output = BytesIO()
        image.save(output, format="JPEG", quality=95)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode(
            "ascii"
        )


def _student_photo(student):
    if student.photo_path:
        try:
            return _image_data(photo_file(student.photo_path), square=True)
        except (OSError, ValueError, AppException):
            pass
    return _image_data(FALLBACK_PHOTO, square=True)


def _watermark(config):
    if not config.watermark_enabled:
        return ""
    try:
        data = _image_data(photo_file(config.logo_path))
    except (OSError, ValueError, AppException):
        return ""
    text_width = min(_text_width(config.school_name, 26, 400), 650)
    left = (800 - (54 + 16 + text_width)) / 2
    logo = f'<image x="{left:.3f}" y="46" width="54" height="54" href="{data}"/>'
    name = _text(
        config.school_name,
        left + 70,
        84,
        26,
        weight=400,
        max_width=650,
    )
    # Only the top margin; the barcode and its white quiet zone never overlap it.
    return f'<g data-watermark="true" opacity="0.45">{logo}{name}</g>'


def render_student_card(student, config: CardSettings) -> str:
    """Render one self-contained, vector card, without any route/auth dependency."""
    try:
        barcode = Code128(student.nisn).build()[0]
        # Align the bars with the photo and text; whitespace stays in the card's
        # outer margins instead of adding padding inside the content container.
        module = 720 / len(barcode)
        bars = "".join(
            f'<rect x="{40 + run.start() * module:.4f}" y="1050" width="{len(run[0]) * module:.4f}" height="70"/>'
            for run in re.finditer("1+", barcode)
        )
        name = "".join(
            _text(line, 40, y, 48, weight=700) for line, y in _name_lines(student.name)
        )
        nisn = _text("NISN", 40, 998, 25, fill="#384240") + _text(
            student.nisn, 114, 998, 25, weight=700, max_width=646
        )
        hint = _text(
            "jaga barcode dari coretan, lipatan, atau goresan",
            40,
            1142,
            16,
            fill="#64706c",
        )
        photo = _student_photo(student)
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1280" viewBox="0 0 800 1280" role="img">'
            f"<title>{escape(student.name)} · NISN {escape(student.nisn)}</title>"
            '<defs><clipPath id="photo"><rect x="40" y="136" width="720" height="720" rx="30"/></clipPath></defs>'
            '<rect x="1" y="1" width="798" height="1278" rx="30" fill="#ffffff" stroke="#64706c" stroke-width="2"/>'
            f"{_watermark(config)}"
            f'<image x="40" y="136" width="720" height="720" clip-path="url(#photo)" href="{photo}"/>'
            f"{name}{nisn}"
            '<rect x="4" y="1040" width="792" height="90" fill="white"/>'
            f'<g data-barcode="{escape(student.nisn, {chr(34): "&quot;"})}" fill="black">{bars}</g>{hint}</svg>'
        )
    except Exception as exc:
        logger.exception("Student card rendering failed for student %s", student.id)
        raise AppException(
            "Kartu siswa gagal dibuat. Periksa identitas dan foto siswa, lalu coba lagi.",
            422,
        ) from exc


def render_student_card_png(student, config: CardSettings) -> bytes:
    svg = render_student_card(student, config)
    # Whole 5:8 pixel units, rounded up, retain the ratio at at least 300 DPI.
    units = ceil(float(config.width_mm) * PRINT_DPI / (25.4 * 5))
    width, height = int(units * 5), int(units * 8)
    try:
        raw = cairosvg.svg2png(
            bytestring=svg.encode(), output_width=width, output_height=height
        )
        with Image.open(BytesIO(raw)) as image:
            output = BytesIO()
            dpi = width / float(config.width_mm) * 25.4
            image.save(output, format="PNG", dpi=(dpi, dpi))
            return output.getvalue()
    except Exception as exc:
        logger.exception("Student card PNG generation failed")
        raise AppException(
            "Gambar kartu gagal dibuat. Silakan coba lagi.", 500
        ) from exc


def card_filename(student) -> str:
    def slug(value):
        ascii_text = (
            unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        )
        return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")

    identity = slug(student.nisn) or "nisn"
    if not re.fullmatch(r"[0-9]{10}", student.nisn):
        identity += f"-{student.id}"  # Legacy non-numeric NISNs may sanitize alike.
    return f"{identity}-{slug(student.name)[:100] or 'siswa'}.png"


def prepare_student_cards_for_print(students, config):
    """Yield one SVG data URI at a time for the shared print document template."""
    for student in students:
        svg = render_student_card(student, config)
        yield {
            "name": student.name,
            "uri": "data:image/svg+xml;base64,"
            + base64.b64encode(svg.encode()).decode(),
        }


def create_student_card_zip(students, config):
    """Return a seekable temporary archive. Caller must close it after delivery."""
    archive = TemporaryFile(mode="w+b")  # noqa: SIM115 — caller owns file lifetime
    try:
        count = 0
        with ZipFile(archive, "w", compression=ZIP_STORED, allowZip64=True) as output:
            for student in students:
                output.writestr(
                    card_filename(student), render_student_card_png(student, config)
                )
                count += 1
        if not count:
            raise AppException("Tidak ada siswa untuk dibuatkan kartu.", 422)
        archive.seek(0)
        return archive
    except Exception as exc:
        archive.close()
        if isinstance(exc, AppException):
            raise
        logger.exception("Student card ZIP creation failed")
        raise AppException("Arsip kartu gagal dibuat. Silakan coba lagi.", 500) from exc
