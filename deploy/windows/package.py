"""Build a ready-to-run Windows release; compiler tools are CI-only."""

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ARTIFACT = "absensa-windows-amd64.zip"
REQUIRED = (
    "python/python.exe",
    "python/python313._pth",
    "postgres/bin/postgres.exe",
    "postgres/bin/pg_dump.exe",
    "postgres/bin/pg_restore.exe",
    "node/node.exe",
    "chrome/chrome.exe",
    "caddy/caddy.exe",
    "native/libcairo-2.dll",
    "native/archive.dll",
    "winsw.exe",
    "manage.py",
    "process_job.py",
    "runtime.py",
    "host.ps1",
    "absensa.ps1",
    "install.ps1",
    "web/app/main.py",
    "web/windows_archive.py",
    "web/alembic.ini",
    "whatsapp/src/server.js",
    "whatsapp/node_modules/whatsapp-web.js/package.json",
    "release.json",
    "dependencies.lock.json",
    "licenses/NOTICE.txt",
)
NATIVE_REQUIRED = ("libcairo-2.dll", "archive.dll", "build.json")


def validate_native(root):
    missing = [name for name in NATIVE_REQUIRED if not (root / name).is_file()]
    if missing:
        available = ", ".join(sorted(p.name for p in root.glob("*.dll"))) or "none"
        raise ValueError(
            f"Incomplete native libraries: {', '.join(missing)}. "
            f"DLLs found in {root}: {available}. Check the native build step."
        )


def probe_native(root):
    """Load real Windows libraries and dependencies before any runtime downloads."""
    validate_native(root)
    with os.add_dll_directory(str(root.resolve())):
        for filename, function, minimum in (
            ("libcairo-2.dll", "cairo_version", 11000),
            ("archive.dll", "archive_version_number", 3000000),
        ):
            try:
                library = ctypes.CDLL(str((root / filename).resolve()))
                query = getattr(library, function)
                query.argtypes = []
                query.restype = ctypes.c_int
                if query() < minimum:
                    raise ValueError("Unsupported library version")
            except (OSError, AttributeError, ValueError) as exc:
                raise ValueError(
                    f"Cannot load native {filename} and its DLL dependencies: {exc}"
                ) from exc
    print("Native Cairo/libarchive DLLs loaded successfully", flush=True)


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download(item, cache):
    path = cache / item["url"].rsplit("/", 1)[-1]
    if not path.exists():
        if not item["url"].startswith("https://"):
            raise ValueError("Only HTTPS dependencies are allowed")
        with (
            urllib.request.urlopen(item["url"], timeout=120) as response,
            path.open("xb") as output,
        ):
            if not response.url.startswith("https://"):
                raise ValueError("Insecure redirect")
            shutil.copyfileobj(response, output)
    if digest(path) != item["sha256"]:
        raise ValueError("Dependency checksum mismatch: " + path.name)
    return path


def unpack(archive, destination, prefix="", include=None):
    # Upstream bytes have already been verified against the reviewed lock file.
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            if not item.filename.startswith(prefix) or item.is_dir():
                continue
            name = item.filename[len(prefix) :]
            if include and not any(name.startswith(entry) for entry in include):
                continue
            if (
                not name
                or Path(name).is_absolute()
                or ".." in Path(name).parts
                or ":" in name
            ):
                raise ValueError("Unsafe dependency archive")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(item) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)


def validate(root):
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise ValueError("Incomplete Windows payload: " + ", ".join(missing))
    for pattern in ("**/.env", "**/*.key", "**/postgresql.conf", "**/PG_VERSION"):
        if list(root.glob(pattern)):
            raise ValueError("Mutable configuration/secret in release")
    for folder in ("photos", "backups", "data"):
        if (root / folder).exists():
            raise ValueError("Mutable data in release")


def archive(root, output):
    validate(root)
    inventory = {
        p.relative_to(root).as_posix(): digest(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "files.sha256.json"
    }
    (root / "files.sha256.json").write_text(json.dumps(inventory, indent=2) + "\n")
    result = output / ARTIFACT
    with zipfile.ZipFile(
        result, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(root).as_posix())
    shutil.copyfile(ROOT / "install.ps1", output / "install.ps1")
    (output / "SHA256SUMS.windows").write_text(
        "".join(
            f"{digest(output / name)}  {name}\n" for name in (ARTIFACT, "install.ps1")
        )
    )
    return result


def build(args):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 13):
        raise SystemExit("Build requires Windows amd64 and CPython 3.13")
    if not re.fullmatch(
        r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", args.version
    ):
        raise ValueError("Invalid release tag")
    probe_native(args.native)
    lock = json.loads((HERE / "dependencies.lock.json").read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)
    root = args.output / "windows-release"
    root.mkdir()
    for name, prefix, destination in (
        ("python", "", "python"),
        ("node", f"node-v{lock['node']['version']}-win-x64/", "node"),
        ("postgres", "pgsql/", "postgres"),
        ("chrome", "chrome-win64/", "chrome"),
    ):
        unpack(
            download(lock[name], args.cache),
            root / destination,
            prefix,
            include=(
                "bin/",
                "lib/",
                "share/",
                "doc/",
                "server_license.txt",
                "commandlinetools_3rd_party_licenses.txt",
            )
            if name == "postgres"
            else None,
        )
    shutil.copyfile(download(lock["winsw"], args.cache), root / "winsw.exe")
    shutil.copytree(args.native, root / "native")
    # Executables need CRT before Python's DLL search configuration can execute.
    for pattern in ("msvcp*.dll", "vcruntime*.dll", "concrt*.dll"):
        for library in args.native.glob(pattern):
            for folder in ("python", "postgres/bin", "node"):
                shutil.copyfile(library, root / folder / library.name)
    (root / "caddy").mkdir()
    shutil.copyfile(args.caddy, root / "caddy/caddy.exe")
    for name in (
        "manage.py",
        "process_job.py",
        "runtime.py",
        "host.ps1",
        "absensa.ps1",
        "dependencies.lock.json",
    ):
        shutil.copyfile(HERE / name, root / name)
    shutil.copyfile(ROOT / "install.ps1", root / "install.ps1")
    shutil.copyfile(HERE / "README.md", root / "PANDUAN.md")
    ignore = shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".env", "node_modules", "photos", "backups", ".wwebjs*"
    )
    for name in ("app", "alembic", "scripts"):
        shutil.copytree(ROOT / "web" / name, root / "web" / name, ignore=ignore)
    shutil.copyfile(ROOT / "web/alembic.ini", root / "web/alembic.ini")
    shutil.copyfile(HERE / "windows_archive.py", root / "web/windows_archive.py")
    # Same application pins. uvloop is POSIX-only; use the equivalent binary psycopg2
    # wheel and stdlib asyncio on Windows. tzdata supplies the IANA database on Windows.
    requirements = []
    for line in (ROOT / "web/requirements.txt").read_text().splitlines():
        if line.startswith("uvloop=="):
            continue
        requirements.append(line.replace("psycopg2==", "psycopg2-binary=="))
    requirements.append("tzdata==2026.5")
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "requirements.txt"
        path.write_text("\n".join(requirements) + "\n")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                "--no-compile",
                "--target",
                str(root / "python/Lib/site-packages"),
                "--report",
                str(root / "python-install-report.json"),
                "-r",
                str(path),
            ],
            check=True,
        )
    (root / "python/python313._pth").write_text(
        "python313.zip\n.\nLib/site-packages\n..\n../web\nimport site\n"
    )
    shutil.copytree(ROOT / "services/whatsapp", root / "whatsapp", ignore=ignore)
    env = {
        **os.environ,
        "PUPPETEER_SKIP_DOWNLOAD": "true",
        "NODE_ENV": "production",
        "PATH": str(root / "node") + os.pathsep + os.environ["PATH"],
    }
    subprocess.run(
        [
            str(root / "node/node.exe"),
            str(root / "node/node_modules/npm/bin/npm-cli.js"),
            "ci",
            "--omit=dev",
            "--ignore-scripts",
        ],
        cwd=root / "whatsapp",
        env=env,
        check=True,
    )
    # npm is a CI build tool; clients only need the Node executable and app modules.
    shutil.rmtree(root / "node/node_modules")
    for name in (
        "npm",
        "npm.cmd",
        "npm.ps1",
        "npx",
        "npx.cmd",
        "npx.ps1",
        "corepack",
        "corepack.cmd",
    ):
        (root / "node" / name).unlink(missing_ok=True)
    # Licensing and exact build inputs travel with each immutable archive.
    shutil.copytree(HERE / "licenses", root / "licenses")
    shutil.copyfile(HERE / "NOTICE.txt", root / "licenses/NOTICE.txt")
    shutil.copyfile(args.caddy.with_suffix(".build.txt"), root / "caddy/build.txt")
    (root / "release.json").write_text(
        json.dumps(
            {
                "format": 1,
                "version": args.version,
                "platform": "windows",
                "architecture": "amd64",
                "postgres_major": 18,
                "upgrade_from_major": int(args.version.split(".")[0][1:]),
                "source_commit": os.environ.get("GITHUB_SHA", ""),
                "dependencies": lock,
                "native": json.loads(
                    (args.native / "build.json").read_text(encoding="utf-8-sig")
                ),
            },
            indent=2,
        )
        + "\n"
    )
    return archive(root, args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--cache", type=Path, default=ROOT / "dist/downloads")
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--caddy", type=Path, required=True)
    print(build(parser.parse_args()))
