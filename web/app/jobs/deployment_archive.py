"""Offline deployment snapshots. Called only in a short-lived maintenance container."""

import argparse
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

from app.services.backup_crypto_service import (
    EncryptedWriter,
    decrypt_archive,
    encryption_key,
    verify_archive,
)
from app.services.durable_file import publish


def add_tree(archive, root, prefix):
    if not root.is_dir():
        raise ValueError("Direktori sumber tidak tersedia")
    for path in sorted(root.rglob("*")):
        # Chromium leaves Singleton socket/lock symlinks; these are process-local.
        if path.name in {"SingletonLock", "SingletonSocket", "SingletonCookie"}:
            continue
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Berkas khusus tidak boleh masuk cadangan")
        archive.add(
            path,
            arcname=f"{prefix}/{path.relative_to(root).as_posix()}",
            recursive=False,
        )


def safe_unpack(source, destination):
    with tarfile.open(source) as archive:
        total = 0
        seen = set()
        for item in archive:
            name = Path(item.name)
            total += item.size
            if (
                name.is_absolute()
                or "\\" in item.name
                or ":" in item.name
                or any(
                    part.endswith((".", " "))
                    or part.split(".")[0].upper()
                    in {
                        "CON",
                        "PRN",
                        "AUX",
                        "NUL",
                        *[f"COM{i}" for i in range(1, 10)],
                        *[f"LPT{i}" for i in range(1, 10)],
                    }
                    for part in name.parts
                )
                or ".." in name.parts
                or not name.parts
                or item.name.casefold() in seen
                or not (item.isfile() or item.isdir())
                or total > 64 * 1024**3
            ):
                raise ValueError("Arsip tidak aman")
            seen.add(item.name.casefold())
            target = destination / name
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(item) as src, target.open("xb") as out:
                    shutil.copyfileobj(src, out)


def publish_snapshot(partial, destination):
    publish(partial, destination)


def snapshot(destination):
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
            raise ValueError("Cadangan database tidak ditemukan")
        source = Path("/app/backups") / f"{backup.id}.absbackup"
    key = encryption_key()
    verify_archive(source, key)
    partial = destination.with_suffix(".partial")
    with partial.open("xb") as output:
        encrypted = EncryptedWriter(output, key)
        with tarfile.open(fileobj=encrypted, mode="w|") as archive:
            archive.add(source, arcname="database.absbackup", recursive=False)
            add_tree(archive, Path("/snapshot/config"), "config")
            add_tree(archive, Path("/snapshot/whatsapp"), "whatsapp")
            add_tree(archive, Path("/snapshot/caddy"), "caddy")
        encrypted.finish()
    verify_archive(partial, key)
    # Exclusive destination; snapshots are named with random IDs by the manager.
    publish_snapshot(partial, destination)


def unpack(source, destination):
    key = encryption_key()
    destination.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        plain = Path(temporary) / "snapshot.tar"
        decrypt_archive(source, plain, key)
        safe_unpack(plain, destination)
        plain.unlink()
        decrypt_archive(destination / "database.absbackup", plain, key)
        database = destination / "database"
        database.mkdir()
        safe_unpack(plain, database)
        with (database / "database.dump").open("rb") as dump:
            if dump.read(5) != b"PGDMP":
                raise ValueError("Format database tidak sah")
        json.loads((database / "manifest.json").read_text())


def restore_files(source):
    for folder, target, uid in (
        ("database/photos", "/restore/photos", 10001),
        ("whatsapp", "/restore/whatsapp", 1000),
        ("caddy", "/restore/caddy", 0),
    ):
        src, dst = source / folder, Path(target)
        if any(dst.iterdir()):
            raise ValueError("Volume pemulihan harus kosong")
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        for path in [dst, *dst.rglob("*")]:
            os.chown(path, uid, uid)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(
        description="Cadangan lengkap dan pemulihan Absensa"
    )
    parser.add_argument("action", choices=["snapshot", "unpack", "files", "verify"])
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        if args.action == "snapshot":
            snapshot(args.source)
        elif args.action == "unpack":
            unpack(args.source, args.destination)
        elif args.action == "files":
            restore_files(args.source)
        else:
            verify_archive(args.source, encryption_key())
    except Exception:  # noqa: BLE001 - archive errors must not expose secrets
        raise SystemExit(
            "Cadangan/pemulihan gagal. Periksa kunci, ruang disk, izin, dan integritas arsip. Data sumber tetap disimpan."
        ) from None


if __name__ == "__main__":
    main()
