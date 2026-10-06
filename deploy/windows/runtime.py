"""Release entry point. Only immutable code lives beside the embedded interpreter."""

import argparse
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

RELEASE = Path(__file__).resolve().parent
DLL_HANDLES = []


def prepare(data, role="web"):
    env = json.loads(
        (Path(data) / "config" / f"{role}.json").read_text(encoding="utf-8")
    )
    # Discard inherited application configuration; the private file is authoritative.
    for key in list(os.environ):
        if key.startswith(
            ("PG", "PYTHON", "UVICORN", "WHATSAPP", "BACKUP", "BRIDGE", "CHROME")
        ) or key in {
            "DATABASE_URL",
            "TEST_DATABASE_URL",
            "PHOTOS_DIR",
            "CORS_ORIGIN",
            "TIMEZONE",
            "ADMIN_COOKIE_SECURE",
            "ACCESS_COOKIE_SECURE",
            "CF_API_TOKEN",
        }:
            del os.environ[key]
    os.environ.update({k: str(v) for k, v in env.items()})
    os.environ["PATH"] = os.pathsep.join(
        [
            str(RELEASE / "native"),
            str(RELEASE / "postgres/bin"),
            str(RELEASE / "node"),
            os.path.join(os.environ["SystemRoot"], "System32"),
        ]
    )
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["LIBARCHIVE"] = str(RELEASE / "native/archive.dll")
    if os.name == "nt":
        for folder in (RELEASE / "native",):
            DLL_HANDLES.append(os.add_dll_directory(str(folder)))
    sys.path.insert(0, str(RELEASE / "web"))
    os.chdir(RELEASE / "web")
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument(
        "--role",
        choices=["web", "scheduler", "backup", "whatsapp", "caddy", "maintenance"],
        required=True,
    )
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    prepare(args.data, args.role)
    if args.role in {"whatsapp", "caddy"}:
        if args.role == "whatsapp":
            command = [
                str(RELEASE / "node/node.exe"),
                str(RELEASE / "whatsapp/src/server.js"),
            ]
            cwd = args.data / "whatsapp"
        else:
            command = [
                str(RELEASE / "caddy/caddy.exe"),
                "run",
                "--config",
                str(args.data / "config/Caddyfile"),
                "--adapter",
                "caddyfile",
            ]
            cwd = args.data / "caddy"
        raise SystemExit(subprocess.call(command, cwd=cwd))
    modules = {
        "web": "uvicorn",
        "scheduler": "app.jobs.whatsapp_notifications",
        "backup": "app.jobs.backups",
    }
    module = args.arguments[0] if args.role == "maintenance" else modules[args.role]
    arguments = args.arguments[1:] if args.role == "maintenance" else args.arguments
    if args.role == "web":
        arguments = [
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            os.environ["ABSENSA_WEB_PORT"],
            "--proxy-headers",
            "--forwarded-allow-ips",
            "127.0.0.1",
        ]
    sys.argv = [module, *arguments]
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()
