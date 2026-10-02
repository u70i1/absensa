"""Versioned streaming AES-256-GCM archive encryption; no plaintext downloads."""

import base64
import os
from pathlib import Path

from app.core.config import settings
from app.services.exceptions import AppException
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"ABSENSA-BACKUP\x01"
CHUNK = 1024 * 1024
# GCM's per-message bound, slightly reduced for a simple whole-byte limit.
MAX_BYTES = (1 << 36) - 32


def encryption_key() -> bytes:
    try:
        key = base64.b64decode(
            settings.backup_encryption_key.get_secret_value(), validate=True
        )
        if len(key) != 32:
            raise ValueError
        return key
    except ValueError as exc:
        raise AppException(
            "Kunci enkripsi cadangan belum dikonfigurasi dengan benar.", 503
        ) from exc


class EncryptedWriter:
    def __init__(self, output, key: bytes):
        self.output = output
        header = MAGIC + os.urandom(12)
        self.cipher = Cipher(algorithms.AES(key), modes.GCM(header[-12:])).encryptor()
        self.cipher.authenticate_additional_data(header)
        output.write(header)
        self.size = 0

    def write(self, data: bytes) -> int:
        self.size += len(data)
        if self.size > MAX_BYTES:
            raise ValueError("Archive too large")
        self.output.write(self.cipher.update(data))
        return len(data)

    def finish(self) -> None:
        self.output.write(self.cipher.finalize())
        self.output.write(self.cipher.tag)
        self.output.flush()
        os.fsync(self.output.fileno())


def decrypt_archive(source: Path, destination: Path, key: bytes) -> None:
    """Publish plaintext only after authentication; destination must be new."""
    staging = destination.with_name(destination.name + ".partial")
    created = False
    try:
        with source.open("rb") as src:
            fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(fd, "wb") as dst:
                header = src.read(len(MAGIC) + 12)
                if not header.startswith(MAGIC) or len(header) != len(MAGIC) + 12:
                    raise ValueError("Invalid archive")
                size = source.stat().st_size - len(header) - 16
                if size < 0 or size > MAX_BYTES:
                    raise ValueError("Invalid archive size")
                src.seek(-16, os.SEEK_END)
                tag = src.read(16)
                src.seek(len(header))
                cipher = Cipher(
                    algorithms.AES(key), modes.GCM(header[-12:], tag)
                ).decryptor()
                cipher.authenticate_additional_data(header)
                while size:
                    data = src.read(min(CHUNK, size))
                    if not data:
                        raise ValueError("Truncated archive")
                    dst.write(cipher.update(data))
                    size -= len(data)
                dst.write(cipher.finalize())
                dst.flush()
                os.fsync(dst.fileno())
        # Link is atomic and refuses to overwrite an existing destination.
        os.link(staging, destination)
    finally:
        if created:
            staging.unlink(missing_ok=True)
