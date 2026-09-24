"""Bounded archive reading without extracting user-controlled paths to disk."""

import re
from pathlib import PurePosixPath

import libarchive
from app.services.exceptions import AppException

ARCHIVE_SUFFIXES = (
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
)
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 200 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_WORKBOOKS = 100
MAX_WORKBOOK_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
PHOTO_NAME = re.compile(r"^[0-9]{10}\.(?:jpg|jpeg|png|webp)$", re.IGNORECASE)


def is_archive(filename: str) -> bool:
    return filename.lower().endswith(ARCHIVE_SUFFIXES)


def _safe_name(name: str) -> str:
    name = name.replace("\\", "/")
    parts = name.split("/")
    if name.startswith("/") or any(
        part == ".." or ":" in part or "\x00" in part for part in parts
    ):
        raise AppException("Arsip memuat jalur file yang tidak aman.", 422)
    return "/".join(part for part in parts if part not in ("", "."))


def _metadata(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        "__MACOSX" in path.parts
        or path.name in {".DS_Store", "Thumbs.db"}
        or path.name.startswith("~$")
    )


def read_archive(
    content: bytes,
) -> tuple[list[tuple[str, bytes]], dict[str, tuple[str, bytes]]]:
    """Accept root spreadsheets and photos/, optionally inside one wrapper folder."""
    files, seen = {}, set()
    expanded = 0
    # Select the outer container explicitly: format autodetection can otherwise
    # mistake an uncompressed RAR containing XLSX files for the nested ZIP.
    if content.startswith(b"Rar!\x1a\x07\x01\x00"):
        format_name = "rar5"
    elif content.startswith(b"Rar!\x1a\x07\x00"):
        format_name = "rar"
    elif content.startswith(b"7z\xbc\xaf\x27\x1c"):
        format_name = "7zip"
    elif content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        format_name = "zip"
    else:
        format_name = "tar"
    try:
        with libarchive.memory_reader(content, format_name=format_name) as archive:
            for index, entry in enumerate(archive, 1):
                if index > MAX_ENTRIES:
                    raise AppException(
                        "Arsip memuat terlalu banyak file atau folder (maksimal 2.000).",
                        413,
                    )
                name = _safe_name(entry.pathname)
                if entry.linkpath or not (entry.isfile or entry.isdir):
                    raise AppException(
                        "Arsip tidak boleh memuat tautan atau file khusus.", 422
                    )
                if entry.isdir:
                    continue
                limit = (
                    MAX_IMAGE_BYTES
                    if PurePosixPath(name).suffix.lower()
                    in {".jpg", ".jpeg", ".png", ".webp"}
                    else MAX_WORKBOOK_BYTES
                )
                if entry.size is not None and entry.size > limit:
                    raise AppException(
                        f"File {name} terlalu besar (Excel maksimal 10 MB, foto 5 MB).",
                        413,
                    )
                chunks = bytearray()
                for block in entry.get_blocks(65536):
                    expanded += len(block)
                    if (
                        expanded > MAX_EXPANDED_BYTES
                        or len(chunks) + len(block) > limit
                    ):
                        raise AppException(
                            "Isi arsip terlalu besar setelah dibuka (maksimal 200 MB).",
                            413,
                        )
                    chunks.extend(block)
                if _metadata(name):
                    continue
                if not name or name.casefold() in seen:
                    raise AppException(f"Nama file dalam arsip berulang: {name}.", 422)
                seen.add(name.casefold())
                files[name] = bytes(chunks)
    except AppException:
        raise
    except Exception as exc:
        raise AppException(
            "Arsip rusak, terenkripsi, atau format kompresinya tidak didukung. Gunakan arsip tanpa kata sandi.",
            422,
        ) from exc
    # Zipping a directory commonly adds a single enclosing directory.
    if files and all("/" in name for name in files):
        roots = {name.split("/", 1)[0] for name in files}
        if len(roots) == 1 and next(iter(roots)).lower() != "photos":
            files = {name.split("/", 1)[1]: data for name, data in files.items()}
    workbooks, photos = [], {}
    for name, data in sorted(files.items()):
        path = PurePosixPath(name)
        if len(path.parts) == 1 and path.suffix.lower() == ".xlsx":
            workbooks.append((name, data))
        elif (
            len(path.parts) == 2
            and path.parts[0].lower() == "photos"
            and PHOTO_NAME.fullmatch(path.name)
        ):
            nisn = path.stem
            if nisn in photos:
                raise AppException(
                    f"Lebih dari satu foto ditemukan untuk NISN {nisn}.", 422
                )
            photos[nisn] = (name, data)
        else:
            raise AppException(
                f"Struktur arsip tidak sesuai: {name}. Letakkan file .xlsx di root dan foto photos/NISN.jpg, .png, atau .webp.",
                422,
            )
    if not workbooks:
        raise AppException("Arsip tidak memiliki file .xlsx di root.", 422)
    if len(workbooks) > MAX_WORKBOOKS:
        raise AppException("Maksimal 100 file Excel per arsip.", 413)
    return workbooks, photos
