"""Release entry point. Only immutable code lives beside the embedded interpreter."""

import argparse
import os
import runpy
import subprocess
import sys
from pathlib import Path

RELEASE = Path(__file__).resolve().parent
DLL_HANDLES = []


def prepare(data, role="web"):
    from manage import read_json

    env = read_json(Path(data) / "config" / f"{role}.json")
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


def run_child(command, cwd):
    # WinSW sends CTRL_C_EVENT to the console process tree before its 120s
    # timeout. Give Caddy/Node time to flush and close their own resources.
    with subprocess.Popen(command, cwd=cwd) as child:
        try:
            return child.wait()
        except KeyboardInterrupt:
            print("Service stop requested; waiting for child shutdown.", flush=True)
            try:
                code = child.wait(timeout=100)
            except subprocess.TimeoutExpired:
                print("Child shutdown timed out; terminating child.", flush=True)
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                return 0
            # STATUS_CONTROL_C_EXIT may be returned signed or unsigned on Windows.
            return 0 if code in (0, -2, 0xC000013A, -1073741510) else code


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
    try:
        run(args)
    except KeyboardInterrupt:
        if args.role == "maintenance":
            raise
        print(f"Service stop requested: {args.role}.", flush=True)


def run(args):
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
        raise SystemExit(run_child(command, cwd))
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
