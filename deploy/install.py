"""Optional interactive first-time setup for Linux and Linux VMs.

Run: python3 deploy/install.py
Requires Docker Engine and the Docker Compose plugin. Uses only the Python
standard library and the same four services as the manual installation path.
"""

import argparse
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from configure import TIMEZONES, write_config

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "deploy" / "production.env"
MARKER = ROOT / "deploy" / "initialized.json"
LOG = ROOT / "deploy" / "install.log"
COMPOSE = ROOT / "compose.production.yml"


class SetupError(Exception):
    """An expected setup problem with an operator-facing message."""


def choice(prompt: str, default: str) -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or default


def yes(prompt: str, *, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} [{suffix}]: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter y or n.")


def inspect_host() -> None:
    if sys.version_info < (3, 10):
        raise SetupError("Python 3.10 or newer is required to run setup.")
    if not sys.stdin.isatty():
        raise SetupError("Run this setup in an interactive terminal.")
    if not sys.platform.startswith("linux"):
        raise SetupError(
            "Run this script inside Linux. On Windows Server, use its Linux VM."
        )
    if os.environ.get("COMPOSE_PROJECT_NAME") not in (None, "", "absensa"):
        raise SetupError(
            "Unset COMPOSE_PROJECT_NAME to keep Absensa's data volumes stable."
        )
    if shutil.which("docker") is None:
        raise SetupError(
            "Docker is missing. Install Docker Engine and its Compose plugin, "
            "then run this script again."
        )
    for command, expected, message in (
        (
            ["docker", "info", "--format", "{{.OSType}}"],
            "linux",
            "Docker must run Linux containers.",
        ),
        (
            ["docker", "compose", "version", "--short"],
            None,
            "Docker Compose plugin is unavailable.",
        ),
    ):
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        if result.returncode or (expected and result.stdout.strip() != expected):
            if command[1] == "info" and result.returncode:
                raise SetupError(
                    "Docker is not running or this account cannot use it. "
                    "Start Docker and grant this account access, then retry."
                )
            raise SetupError(message)
    free_gb = shutil.disk_usage(ROOT).free / 1024**3
    if free_gb < 5:
        print(
            f"  Warning: only {free_gb:.1f} GB free. Images and school data need space."
        )


def compose(*arguments: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(CONFIG),
        "-f",
        str(COMPOSE),
        *arguments,
    ]


def any_existing_data() -> bool:
    containers = subprocess.run(
        compose("ps", "-a", "-q"), cwd=ROOT, capture_output=True, text=True, check=False
    )
    if containers.returncode:
        raise SetupError("Could not inspect existing Absensa containers.")
    if containers.stdout.strip():
        return True
    for name in ("absensa_pgdata", "absensa_photos", "absensa_whatsapp_auth"):
        volume = subprocess.run(
            ["docker", "volume", "inspect", name],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if volume.returncode == 0:
            return True
    return False


def read_settings() -> tuple[int, str]:
    values = dict(
        line.split("=", 1)
        for line in CONFIG.read_text(encoding="utf-8").splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    )
    try:
        port = int(values["ABSENSA_PORT"])
        timezone = values["TIMEZONE"]
        if not 1024 <= port <= 65535 or timezone not in TIMEZONES:
            raise ValueError
        if (
            len(values["POSTGRES_PASSWORD"]) < 32
            or len(values["WHATSAPP_BRIDGE_TOKEN"]) < 32
        ):
            raise ValueError
    except (KeyError, ValueError) as exc:
        raise SetupError(
            "The existing production.env is incomplete. Keep it safe and "
            "review it with a technical helper; do not regenerate its passwords."
        ) from exc
    return port, timezone


def free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def choose_settings() -> tuple[int, str]:
    if CONFIG.exists():
        port, timezone = read_settings()
        print(f"  Existing settings found: port {port}, {timezone}.")
        print(
            "  Internal passwords will be reused; they will not be displayed or changed."
        )
        return port, timezone
    while True:
        answer = choice("Web port for the school LAN", "8088")
        try:
            port = int(answer)
        except ValueError:
            print("Enter a number from 1024 to 65535.")
            continue
        if not 1024 <= port <= 65535:
            print("Enter a number from 1024 to 65535.")
        elif not free_port(port):
            print(f"Port {port} is already in use. Choose another port.")
        else:
            break
    print("School time zone: 1) Jakarta/WIB  2) Makassar/WITA  3) Jayapura/WIT")
    while True:
        answer = choice("Time zone", "1")
        if answer in ("1", "2", "3"):
            timezone = TIMEZONES[int(answer) - 1]
            break
        print("Choose 1, 2 or 3.")
    try:
        write_config(CONFIG, port, timezone)
    except FileExistsError as exc:
        raise SetupError(
            "Settings appeared during setup. Run the script again."
        ) from exc
    print("  Private database and bridge passwords generated and saved locally.")
    return port, timezone


def run_step(label: str, command: list[str], log) -> None:
    print(f"  {label} ...", end="", flush=True)
    log.write(f"\n{label}\n")
    log.flush()
    process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    frames = "|/-\\"
    index = 0
    try:
        while process.poll() is None:
            print(f"\r  {label} ... {frames[index % len(frames)]}", end="", flush=True)
            index += 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        raise
    if process.returncode:
        print(f"\r  {label} ... failed")
        raise SetupError(f"{label} failed. Details: {LOG}")
    print(f"\r  {label} ... done")


def read_admin() -> tuple[str, str]:
    while True:
        username = choice("Administrator username", "admin").strip().casefold()
        if 1 <= len(username) <= 100:
            break
        print("Use a username of 1 to 100 characters.")
    while True:
        password = getpass.getpass("Administrator password (8+ characters): ")
        if not 8 <= len(password) <= 1024:
            print("Use 8 to 1024 characters.")
            continue
        if password != getpass.getpass("Repeat administrator password: "):
            print("Passwords did not match. Try again.")
            continue
        return username, password


def create_admin(username: str, password: str) -> None:
    # Never put the password in argv, the environment, or the Docker build log.
    result = subprocess.run(
        compose(
            "exec",
            "-T",
            "web",
            "python",
            "-m",
            "scripts.create_admin",
            "--password-stdin",
            username,
        ),
        cwd=ROOT,
        input=password + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise SetupError(
            "Could not create the administrator. Check the web logs and retry."
        )


def check_web(port: int) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/health", timeout=10) as response:
            if response.status != 200:
                raise SetupError("The web health check failed. Review the web logs.")
    except (OSError, urllib.error.URLError) as exc:
        raise SetupError("The web health check failed. Review the web logs.") from exc


def mark_initialized(port: int, timezone: str, username: str) -> None:
    data = json.dumps({"port": port, "timezone": timezone, "admin": username}) + "\n"
    fd = os.open(MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as target:
        target.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Retry an interrupted setup with the existing settings and volumes",
    )
    args = parser.parse_args()
    print("\nAbsensa server setup\n" + "=" * 20)
    inspect_host()
    if MARKER.exists():
        print(
            "Absensa was already initialized here. Use the update guide for new versions."
        )
        return
    if CONFIG.exists() and any_existing_data() and not args.resume:
        raise SetupError(
            "Existing Absensa data was found. Setup stopped to protect it. "
            "If an earlier setup was interrupted, rerun with --resume."
        )
    if args.resume and not CONFIG.exists():
        raise SetupError("No existing settings were found. Run setup without --resume.")
    if args.resume:
        print("  Resume will reuse the current database and secrets.")
        print("  Use the update guide if the application source has changed.")
        if not yes("Continue the interrupted setup?"):
            print("Setup canceled.")
            return
    port, timezone = choose_settings()
    print(f"\n  Address: http://<server-LAN-IP>:{port}/admin")
    print(f"  Time zone: {timezone}")
    print("  Services: web, notifications, WhatsApp, PostgreSQL")
    if not yes("Build and start Absensa with these settings?"):
        print("Setup canceled. Settings were kept for a later attempt.")
        return
    fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(LOG, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as log:
        run_step("Checking configuration", compose("config", "--quiet"), log)
        run_step("Building application images", compose("build", "--quiet"), log)
        run_step(
            "Starting services and applying database migrations",
            compose("up", "-d", "--wait", "--wait-timeout", "180", "--no-build"),
            log,
        )
    check_web(port)
    print("\n  Application is healthy. Create its administrator account.")
    if args.resume:
        print("  Reusing an existing username will reset that account's password.")
    username, password = read_admin()
    create_admin(username, password)
    if not MARKER.exists():
        mark_initialized(port, timezone, username)
    print("\nAbsensa is ready.")
    print(f"  On this server: http://localhost:{port}/admin")
    print(f"  On the school LAN: http://<server-LAN-IP>:{port}/admin")
    print("  Allow only this web port from your school LAN and test from another PC.")
    print("  Link WhatsApp from the admin dashboard when needed.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print(
            "\nSetup interrupted. Settings and data were kept. Retry with --resume if needed."
        )
        raise SystemExit(130) from None
    except SetupError as exc:
        print(f"\nSetup stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
