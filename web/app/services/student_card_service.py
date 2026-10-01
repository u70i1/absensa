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
from app.schemas.student_card import CARD_HEIGHT_MM, CARD_WIDTH_MM, CardSettings
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
CARD_CANVAS_WIDTH = float(CARD_WIDTH_MM) * 10
CARD_CANVAS_HEIGHT = float(CARD_HEIGHT_MM) * 10
PHOTO_X, PHOTO_Y = 48, 111
PHOTO_HEIGHT = CARD_CANVAS_HEIGHT - PHOTO_Y - 48
PHOTO_WIDTH = PHOTO_HEIGHT * 3 / 4
DETAILS_X = PHOTO_X + PHOTO_WIDTH + 32
DETAILS_WIDTH = CARD_CANVAS_WIDTH - 48 - DETAILS_X
BARCODE_Y = PHOTO_Y + PHOTO_HEIGHT - 96
_font_lock = RLock()


@lru_cache(maxsize=3)
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
    if _text_width(name, 36, 700) <= DETAILS_WIDTH:
        return [(name, 146)]
    words = name.split()
    if len(words) == 1:
        return [(name, 146)]
    split = min(
        range(1, len(words)),
        key=lambda i: max(
            _text_width(" ".join(words[:i]), 36, 700),
            _text_width(" ".join(words[i:]), 36, 700),
        ),
    )
    return [(" ".join(words[:split]), 146), (" ".join(words[split:]), 190)]


def _image_data(path, *, size=None):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if size:
            image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
        else:
            image.thumbnail((512, 512))
        output = BytesIO()
        image.save(output, format="JPEG", quality=95)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode(
            "ascii"
        )


def _student_photo(student, size):
    if student.photo_path:
        try:
            return _image_data(photo_file(student.photo_path), size=size)
        except (OSError, ValueError, AppException):
            pass
    return _image_data(FALLBACK_PHOTO, size=size)


def _attendance_label():
    label = "Kartu Presensi Absensa"
    width = _text_width(label, 12, 600) + 24
    left = CARD_CANVAS_WIDTH - 48 - width
    return (
        f'<rect x="{left}" y="48" width="{width}" height="31" rx="15.5" fill="white" stroke="#656f6e"/>'
        + _text(
            label, left + 12, 70, 12, weight=600, fill="#2e3837", max_width=width - 24
        )
    )


def _watermark(config, *, logo_data=None):
    if not config.watermark_enabled:
        return ""
    if logo_data is None:
        try:
            logo_data = _image_data(photo_file(config.logo_path))
        except (OSError, ValueError, AppException):
            return ""
    # Match the Figma header; long school names shrink before reaching the badge.
    badge_width = _text_width("Kartu Presensi Absensa", 12, 600) + 24
    max_width = CARD_CANVAS_WIDTH - 96 - badge_width - 32 - 28
    logo = f'<image x="48" y="53.5" width="20" height="20" href="{logo_data}"/>'
    name = _text(config.school_name, 76, 70.5, 18, fill="#161d1c", max_width=max_width)
    return f'<g data-watermark="true" opacity="0.7">{logo}{name}</g>'


def render_student_card(student, config: CardSettings, *, logo_data=None) -> str:
    """Render the fixed landscape design with a centered 3:4 photo crop."""
    try:
        barcode = Code128(student.nisn).build()[0]
        module = DETAILS_WIDTH / len(barcode)
        bars = "".join(
            f'<rect x="{DETAILS_X + run.start() * module:.4f}" y="{BARCODE_Y}" width="{len(run[0]) * module:.4f}" height="72"/>'
            for run in re.finditer("1+", barcode)
        )
        lines = _name_lines(student.name)
        name = "".join(
            _text(
                line,
                DETAILS_X,
                y,
                36,
                weight=700,
                fill="#161d1c",
                max_width=DETAILS_WIDTH,
            )
            for line, y in lines
        )
        nisn_y = 183 + (len(lines) - 1) * 44
        label_width = _text_width("NISN ", 18, 400)
        nisn = _text("NISN ", DETAILS_X, nisn_y, 18, fill="#2e3837") + _text(
            student.nisn,
            DETAILS_X + label_width,
            nisn_y,
            18,
            weight=700,
            fill="#161d1c",
            max_width=DETAILS_WIDTH - label_width,
        )
        hint = _text(
            "jaga barcode ini dari coretan, lipatan, atau goresan",
            DETAILS_X,
            PHOTO_Y + PHOTO_HEIGHT - 2,
            10,
            fill="#626b6a",
            max_width=DETAILS_WIDTH,
        )
        photo = _student_photo(student, (768, 1024))
        photo_bounds = (
            f'x="{PHOTO_X}" y="{PHOTO_Y}" width="{PHOTO_WIDTH}" height="{PHOTO_HEIGHT}"'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_CANVAS_WIDTH:g}" height="{CARD_CANVAS_HEIGHT:g}" viewBox="0 0 {CARD_CANVAS_WIDTH:g} {CARD_CANVAS_HEIGHT:g}" role="img">'
            f"<title>{escape(student.name)} · NISN {escape(student.nisn)}</title>"
            f'<defs><clipPath id="photo"><rect {photo_bounds} rx="16"/></clipPath></defs>'
            f'<rect x="0.5" y="0.5" width="{CARD_CANVAS_WIDTH - 1:g}" height="{CARD_CANVAS_HEIGHT - 1:g}" rx="16" fill="#f4fbf9" stroke="#656f6e"/>'
            f"{_watermark(config, logo_data=logo_data)}{_attendance_label()}"
            f'<image {photo_bounds} preserveAspectRatio="xMidYMid slice" clip-path="url(#photo)" href="{photo}"/>'
            f"{name}{nisn}"
            f'<rect x="{DETAILS_X}" y="{BARCODE_Y}" width="{DETAILS_WIDTH}" height="72" fill="white"/>'
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
    width = ceil(float(CARD_WIDTH_MM) * PRINT_DPI / 25.4)
    height = ceil(float(CARD_HEIGHT_MM) * PRINT_DPI / 25.4)
    try:
        raw = cairosvg.svg2png(
            bytestring=svg.encode(), output_width=width, output_height=height
        )
        with Image.open(BytesIO(raw)) as image:
            output = BytesIO()
            # Independent DPI values account for whole-pixel rounding on each axis.
            dpi = (
                width / float(CARD_WIDTH_MM) * 25.4,
                height / float(CARD_HEIGHT_MM) * 25.4,
            )
            image.save(output, format="PNG", dpi=dpi)
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
