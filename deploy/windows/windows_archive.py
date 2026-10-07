"""Windows adapter for the shared authenticated .absbackup/.absfull archive format."""

import base64
import json
import sys
import tarfile
import tempfile
from pathlib import Path

from app.core.config import settings
from app.jobs.deployment_archive import add_tree, publish_snapshot, safe_unpack
from app.services.backup_crypto_service import (
    EncryptedWriter,
    decrypt_archive,
    encryption_key,
    verify_archive,
)


def snapshot(destination, data):
    from app.db.session import SessionLocal
    from app.models.backup import Backup
    from sqlalchemy import select

    with SessionLocal() as db:
        backup = db.scalar(
            select(Backup)
            .where(Backup.status == "success")
            .order_by(Backup.created_at.desc())
        )
        if backup is None:
            raise ValueError("Cadangan database belum tersedia")
        source = Path(settings.backups_dir) / (backup.id + ".absbackup")
    config = json.loads((data / "config/installation.json").read_text())
    key = encryption_key()
    verify_archive(source, key)
    partial = destination.with_suffix(".partial")
    with partial.open("xb") as output:
        encrypted = EncryptedWriter(output, key)
        with tarfile.open(fileobj=encrypted, mode="w|") as archive:
            archive.add(source, arcname="database.absbackup", recursive=False)
            archive.add(
                data / "config/installation.json",
                arcname="config/installation.json",
                recursive=False,
            )
            archive.add(
                data / "state.json", arcname="config/state.json", recursive=False
            )
            add_tree(archive, data / "whatsapp" / config["whatsapp_tree"], "whatsapp")
            add_tree(archive, data / "caddy" / config["caddy_tree"], "caddy")
        encrypted.finish()
    verify_archive(partial, key)
    publish_snapshot(partial, destination)


def unpack(source, destination, key_file):
    key = base64.b64decode(key_file.read_text().strip(), validate=True)
    if len(key) != 32:
        raise ValueError("Kunci tidak sah")
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        plain = Path(temporary) / "archive.tar"
        decrypt_archive(source, plain, key)
        if source.suffix == ".absfull":
            safe_unpack(plain, destination)
            plain.unlink()
            decrypt_archive(destination / "database.absbackup", plain, key)
        elif source.suffix != ".absbackup":
            raise ValueError("Gunakan .absfull atau .absbackup")
        database = destination / "database"
        database.mkdir()
        safe_unpack(plain, database)
        if (database / "database.dump").open("rb").read(5) != b"PGDMP":
            raise ValueError("Format database tidak sah")
        metadata = json.loads((database / "manifest.json").read_text())
        if metadata.get("version") != 1 or not (database / "photos").is_dir():
            raise ValueError("Manifest/foto tidak tersedia")


def main():
    try:
        if sys.argv[1] == "snapshot":
            snapshot(Path(sys.argv[2]), Path(sys.argv[3]))
        elif sys.argv[1] == "unpack":
            unpack(*map(Path, sys.argv[2:5]))
        else:
            raise ValueError("Operasi tidak dikenal")
    except Exception:  # noqa: BLE001 - CLI boundary must not disclose backup secrets.
        raise SystemExit(
            "Cadangan/pemulihan gagal. Periksa kunci, integritas arsip, izin dan ruang disk. Data sumber dipertahankan."
        ) from None


if __name__ == "__main__":
    main()
