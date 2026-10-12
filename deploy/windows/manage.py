"""Native Windows deployment backend. Runtimes arrive in a verified release ZIP."""

import argparse
import base64
import contextlib
import getpass
import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

RELEASE = Path(__file__).resolve().parent
SERVICES = {
    "postgres": "AbsensaPostgreSQL",
    "web": "AbsensaWeb",
    "scheduler": "AbsensaScheduler",
    "backup": "AbsensaBackup",
    "whatsapp": "AbsensaWhatsApp",
    "caddy": "AbsensaCaddy",
}
APPLICATION = ("web", "scheduler", "backup", "whatsapp", "caddy")
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


class OperationError(Exception):
    pass


def say(message):
    print(message, flush=True)


def version(value):
    if not TAG.fullmatch(value):
        raise OperationError("Versi rilis tidak sah.")
    return tuple(map(int, value[1:].split(".")))


def atomic(path, content):
    from app.services.durable_file import publish

    temporary = path.with_name(path.name + ".new-" + secrets.token_hex(4))
    with temporary.open("x", encoding="utf-8", newline="\n") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    publish(temporary, path, replace=True)


def write_json(path, value):
    atomic(path, json.dumps(value, indent=2) + "\n")


def read_json(path):
    """Accept UTF-8 with/without BOM; never recover by inventing configuration."""
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeError:
        raise OperationError(f"{path}: encoding harus UTF-8 (BOM diperbolehkan). Pulihkan salinan konfigurasi yang valid; jangan membuat rahasia baru.") from None
    except json.JSONDecodeError as exc:
        raise OperationError(f"{path}: JSON tidak sah pada baris {exc.lineno}, kolom {exc.colno}. Pulihkan salinan konfigurasi yang valid; jangan mengedit state untuk melewati repair.") from None
    except OSError as exc:
        raise OperationError(f"{path}: tidak dapat dibaca ({type(exc).__name__}); periksa file dan izin.") from None
    if not isinstance(value, dict) or not value:
        raise OperationError(f"{path}: objek JSON tidak kosong diperlukan.")
    return value


def require_fields(path, value, fields):
    missing = sorted(set(fields) - value.keys())
    if missing:
        raise OperationError(f"{path}: field wajib tidak ada: {', '.join(missing)}. Pulihkan konfigurasi yang valid.")


def validate_host(value):
    try:
        address = ipaddress.IPv4Address(value)
        if address.is_unspecified or address.is_multicast or address.is_loopback:
            raise OperationError("Gunakan IPv4 LAN tetap server.")
        return str(address)
    except ipaddress.AddressValueError:
        if (
            len(value) > 253
            or "." not in value
            or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                for part in value.split(".")
            )
        ):
            raise OperationError(
                "Isi nama DNS huruf kecil atau IPv4 LAN, tanpa https:// atau port."
            )
        return value


def new_config(host, port=443, timezone="Asia/Jakarta", tls="internal", token=""):
    validate_host(host)
    if (
        not 1 <= port <= 65535
        or port in (55438, 18088, 13001)
        or timezone not in ("Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura")
        or tls not in ("internal", "cloudflare")
    ):
        raise OperationError("Port, zona waktu, atau mode HTTPS tidak sah.")
    if tls == "cloudflare" and (
        re.fullmatch(r"[0-9.]+", host)
        or not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token)
    ):
        raise OperationError(
            "Cloudflare memerlukan nama domain dan token DNS zona sekolah."
        )
    return {
        "format": 1,
        "host": host,
        "https_port": port,
        "tls": tls,
        "timezone": timezone,
        "cf_token": token,
        "pg_port": 55438,
        "web_port": 18088,
        "bridge_port": 13001,
        "pg_password": secrets.token_hex(32),
        "db_password": secrets.token_hex(32),
        "bridge_token": secrets.token_hex(32),
        "backup_key": base64.b64encode(secrets.token_bytes(32)).decode(),
        "database": "absensa",
        "photo_tree": "live",
        "whatsapp_tree": "live",
        "caddy_tree": "live",
    }


def caddyfile(config):
    tls = (
        "tls internal"
        if config["tls"] == "internal"
        else "tls {\n        dns cloudflare {env.CF_API_TOKEN}\n    }"
    )
    return (
        "{\n    auto_https disable_redirects\n    admin off\n    skip_install_trust\n    servers {\n        protocols h1 h2\n    }\n}\n"
        f"https://{config['host']}:{config['https_port']} {{\n    {tls}\n"
        "    header Strict-Transport-Security max-age=31536000\n"
        f"    reverse_proxy 127.0.0.1:{config['web_port']}\n}}\n"
    )


def https_health(host, port, context):
    # Python verifies IP SANs but omits SNI for IP literals. Caddy then selects
    # its certificate using the connection's destination IP, not the HTTP Host.
    # DNS names stay pinned to loopback: DNS cannot redirect this trusted probe.
    try:
        destination = str(ipaddress.IPv4Address(host))
    except ipaddress.AddressValueError:
        destination = "127.0.0.1"
    connection = http.client.HTTPSConnection(host, port, context=context, timeout=5)
    try:
        with socket.create_connection((destination, port), timeout=5) as sock:
            connection.sock = context.wrap_socket(sock, server_hostname=host)
        connection.request("GET", "/health")
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def service_xml(role, release, data):
    root = ET.Element("service")

    def add(name, value):
        ET.SubElement(root, name).text = str(value)

    add("id", SERVICES[role])
    add(
        "name",
        "Absensa "
        + {
            "web": "Web",
            "scheduler": "Penjadwal WhatsApp",
            "backup": "Cadangan",
            "whatsapp": "WhatsApp",
            "caddy": "HTTPS",
        }[role],
    )
    add("description", "Absensa native Windows; konfigurasi dan data di " + str(data))
    add("executable", release / "python/python.exe")
    add(
        "arguments",
        subprocess.list2cmdline(
            [str(release / "runtime.py"), "--data", str(data), "--role", role]
        ),
    )
    add("workingdirectory", release / "web")
    add("startmode", "Manual")  # Enabled only after migration + verified health.
    add("stoptimeout", "120 sec")
    add("logpath", data / "logs" / role)
    log = ET.SubElement(root, "log", mode="roll-by-size")
    ET.SubElement(log, "sizeThreshold").text = "10240"
    ET.SubElement(log, "keepFiles").text = "5"
    ET.SubElement(root, "onfailure", action="restart", delay="15 sec")
    add("depend", SERVICES["web"] if role == "caddy" else SERVICES["postgres"])
    account = ET.SubElement(root, "serviceaccount")
    ET.SubElement(account, "username").text = "NT AUTHORITY\\LocalService"
    return ET.tostring(root, encoding="unicode") + "\n"


@contextlib.contextmanager
def operation_lock(data):
    # Kernel lock is released on crash; no stale PID file or timed lock stealing.
    import msvcrt

    with (data / "operation.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise OperationError(
                "Pemeliharaan lain masih berjalan. Tunggu sampai selesai."
            ) from exc
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


class Installation:
    def __init__(self, root, data):
        self.root, self.data = Path(root), Path(data)
        if (
            not self.root.is_absolute()
            or not self.data.is_absolute()
            or self.root.is_relative_to(self.data)
            or self.data.is_relative_to(self.root)
        ):
            raise OperationError(
                "Binary dan data harus dua direktori absolut yang terpisah."
            )
        for directory in (self.root, self.data):
            if any(
                p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
                for p in (directory, *directory.parents)
            ):
                raise OperationError(
                    "Direktori instalasi tidak boleh melewati junction/tautan."
                )
        self.state_path = self.data / "state.json"
        self.config_path = self.data / "config/installation.json"
        self.state = read_json(self.state_path) if self.state_path.exists() else None
        self.config = read_json(self.config_path) if self.config_path.exists() else None
        if self.state is not None:
            require_fields(self.state_path, self.state, ("format", "version", "root", "data", "initialized"))
            if not isinstance(self.state["version"], str):
                raise OperationError(f"{self.state_path}: version harus berupa teks tag rilis.")
            version(self.state["version"])
            if (self.state["format"] != 1 or self.state["root"] != str(self.root)
                    or self.state["data"] != str(self.data)):
                raise OperationError("Identitas instalasi berubah. Pulihkan konfigurasi; jangan pindahkan direktori secara manual.")
            for field in ("initialized", "autostart", "uninstalled"):
                if field in self.state and type(self.state[field]) is not bool:
                    raise OperationError(f"{self.state_path}: {field} harus boolean.")
            if "transaction" in self.state:
                transaction = self.state["transaction"]
                if not isinstance(transaction, dict) or transaction.get("phase") not in {
                    "install", "migration", "backup", "restore", "restored", "repair", "finalize"
                }:
                    raise OperationError(f"{self.state_path}: transaction/phase tidak sah. Pulihkan jurnal yang valid.")
                if transaction["phase"] == "backup" and (
                    not isinstance(transaction.get("resume"), list)
                    or any(role not in APPLICATION for role in transaction["resume"])
                ):
                    raise OperationError(f"{self.state_path}: transaction/resume tidak sah.")
            if self.config is None:
                raise OperationError(f"{self.config_path}: konfigurasi hilang; pulihkan salinan asli. Rahasia tidak dibuat ulang.")
        if self.config is not None:
            c = self.config
            require_fields(self.config_path, c, (
                "format", "host", "https_port", "tls", "timezone", "cf_token", "pg_port",
                "web_port", "bridge_port", "pg_password", "db_password", "bridge_token",
                "backup_key", "database", "photo_tree", "whatsapp_tree", "caddy_tree",
            ))
            text_fields = ("host", "tls", "timezone", "cf_token", "pg_password", "db_password",
                           "bridge_token", "backup_key", "database", "photo_tree", "whatsapp_tree", "caddy_tree")
            for field in text_fields:
                if not isinstance(c[field], str):
                    raise OperationError(f"{self.config_path}: {field} harus berupa teks.")
            validate_host(c["host"])
            ports = [c[field] for field in ("https_port", "pg_port", "web_port", "bridge_port")]
            if (any(type(port) is not int or not 1 <= port <= 65535 for port in ports)
                    or len(set(ports)) != 4):
                raise OperationError(f"{self.config_path}: port harus integer 1–65535 dan berbeda.")
            if (c["format"] != 1 or c["tls"] not in ("internal", "cloudflare")
                    or c["timezone"] not in ("Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura")):
                raise OperationError(f"{self.config_path}: format, tls, atau timezone tidak sah.")
            if c["tls"] == "cloudflare" and (
                re.fullmatch(r"[0-9.]+", c["host"])
                or not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", c["cf_token"])
            ):
                raise OperationError(f"{self.config_path}: Cloudflare memerlukan domain dan token DNS yang valid.")
            for name in ("database", "photo_tree", "whatsapp_tree", "caddy_tree"):
                if not re.fullmatch(r"[a-z0-9_]+", c[name]):
                    raise OperationError(f"{self.config_path}: nama penyimpanan {name} tidak sah.")
            for field in ("pg_password", "db_password", "bridge_token"):
                if not re.fullmatch(r"[a-f0-9]{64}", c[field]):
                    raise OperationError(f"{self.config_path}: {field} tidak sah; pulihkan rahasia asli.")
            try:
                valid_key = len(base64.b64decode(c["backup_key"], validate=True)) == 32
            except ValueError:
                valid_key = False
            if not valid_key:
                raise OperationError(f"{self.config_path}: backup_key tidak sah; pulihkan kunci asli.")

    @property
    def release(self):
        return self.root / "releases" / self.state["version"]

    @property
    def python(self):
        return self.release / "python/python.exe"

    def run(
        self, args, *, input=None, env=None, check=True, timeout=900, operation=None,
        expected_codes=(0,),
    ):
        result = subprocess.run(
            [str(a) for a in args],
            input=input,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if result.returncode not in expected_codes:
            operation = operation or Path(args[0]).name
            self.diagnostic(f"{operation}: exit {result.returncode}\n{result.stdout}{result.stderr}")
            if check:
                raise OperationError(
                    f"Operasi {operation} gagal. Periksa {self.data / 'logs/operations.log'}."
                )
        return result

    def redact(self, message):
        for key in ("pg_password", "db_password", "bridge_token", "backup_key", "cf_token"):
            if self.config and self.config.get(key):
                message = message.replace(self.config[key], "[RAHASIA]")
        # Also redact connection URLs if a driver includes one in an exception.
        return re.sub(r"(://)[^/\s@]+@", r"\1[RAHASIA]@", message)

    def diagnostic(self, message):
        message = self.redact(message)
        directory = self.data / "logs"
        directory.mkdir(exist_ok=True)
        with (directory / "operations.log").open("a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")
        return message

    def host(self, action, **values):
        command = [
            os.path.join(
                os.environ["SystemRoot"],
                "System32/WindowsPowerShell/v1.0/powershell.exe",
            ),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            RELEASE / "host.ps1",
            "-Action",
            action,
        ]
        for key, value in values.items():
            command.extend(["-" + key, str(value)])
        # Include the host action and service, never the full argument list or secrets.
        operation = f"host.ps1 {action}"
        if values.get("Name"):
            operation += f" ({values['Name']})"
        return self.run(command, operation=operation)

    def save(self):
        write_json(self.state_path, self.state)

    def sc(self, *args, **kwargs):
        return self.run(
            [os.path.join(os.environ["SystemRoot"], "System32/sc.exe"), *args], **kwargs
        )

    def exists(self, role):
        result = self.sc("query", SERVICES[role], check=False, expected_codes=(0, 1060))
        if result.returncode not in (0, 1060):
            raise OperationError("Status layanan tidak dapat diperiksa.")
        return result.returncode == 0

    def running(self, role):
        result = self.sc("query", SERVICES[role], check=False, expected_codes=(0, 1060))
        if result.returncode not in (0, 1060):
            raise OperationError("Status layanan tidak dapat diperiksa: " + SERVICES[role])
        return result.returncode == 0 and bool(re.search(r":\s+4\s", result.stdout))

    def set_start(self, automatic):
        for role, name in SERVICES.items():
            if self.exists(role):
                self.sc(
                    "config",
                    name,
                    "start=",
                    "auto" if automatic else "demand",
                )

    def stop(self, roles=tuple(SERVICES)):
        for role in reversed(roles):
            if not self.exists(role):
                continue
            result = self.sc("stop", SERVICES[role], check=False, expected_codes=(0, 1062))
            if result.returncode not in (0, 1062):
                raise OperationError(
                    "Layanan tidak dapat dihentikan: " + SERVICES[role]
                )
            for _ in range(150):
                result = self.sc("query", SERVICES[role])
                if re.search(r":\s+1\s", result.stdout):
                    break
                time.sleep(1)
            else:
                raise OperationError("Layanan belum berhenti: " + SERVICES[role])

    def start_services(self, roles=tuple(SERVICES)):
        for role in roles:
            if not self.running(role):
                self.sc("start", SERVICES[role])
                for _ in range(60):
                    if self.running(role):
                        break
                    time.sleep(1)
                else:
                    raise OperationError("Layanan belum berjalan: " + SERVICES[role])

    def guard(self):
        if not self.state or not self.config:
            raise OperationError("Instalasi belum lengkap. Jalankan kembali installer.")
        if self.state.get("transaction"):
            raise OperationError(
                "Pemeliharaan sebelumnya terhenti. Jalankan repair; jangan menyalakan versi lama setelah migrasi."
            )
        self.storage_check()

    def storage_check(self):
        if self.state.get("initialized"):
            required = [
                self.data / "postgres/PG_VERSION",
                self.data / "photos" / self.config["photo_tree"],
                self.data / "backups",
                self.data / "whatsapp" / self.config["whatsapp_tree"],
                self.data / "caddy" / self.config["caddy_tree"],
            ]
            if not all(p.exists() for p in required):
                raise OperationError(
                    "Penyimpanan data tidak lengkap. Periksa disk; database baru tidak akan dibuat."
                )

    def environment(self, role):
        c, d = self.config, self.data
        common = {
            "TIMEZONE": c["timezone"],
            "DATABASE_URL": f"postgresql+psycopg2://absensa:{c['db_password']}@127.0.0.1:{c['pg_port']}/{c['database']}?connect_timeout=5",
            "PHOTOS_DIR": str(d / "photos" / c["photo_tree"]),
            "BACKUPS_DIR": str(d / "backups"),
            "ADMIN_COOKIE_SECURE": "true",
            "ACCESS_COOKIE_SECURE": "true",
            "CORS_ORIGIN": f"https://{c['host']}"
            + (f":{c['https_port']}" if c["https_port"] != 443 else ""),
            "WHATSAPP_BRIDGE_URL": f"http://127.0.0.1:{c['bridge_port']}",
            "WHATSAPP_BRIDGE_TOKEN": c["bridge_token"],
            "ABSENSA_WEB_PORT": str(c["web_port"]),
        }
        if role in ("backup", "maintenance"):
            common["BACKUP_ENCRYPTION_KEY"] = c["backup_key"]
        if role == "whatsapp":
            common = {
                "BRIDGE_API_TOKEN": c["bridge_token"],
                "BRIDGE_HOST": "127.0.0.1",
                "BRIDGE_PORT": str(c["bridge_port"]),
                "WHATSAPP_AUTH_DIR": str(d / "whatsapp" / c["whatsapp_tree"] / "auth"),
                "WHATSAPP_CACHE_DIR": str(
                    d / "whatsapp" / c["whatsapp_tree"] / "cache"
                ),
                "CHROME_PATH": str(self.release / "chrome/chrome.exe"),
                "CHROME_NO_SANDBOX": "false",
            }
        elif role == "caddy":
            common = {
                "XDG_DATA_HOME": str(d / "caddy" / c["caddy_tree"]),
                "XDG_CONFIG_HOME": str(d / "caddy" / c["caddy_tree"] / "config"),
                "CF_API_TOKEN": c["cf_token"],
            }
        common.update(
            TEMP=str(d / "temp" / role),
            TMP=str(d / "temp" / role),
            ABSENSA_HEARTBEAT_DIR=str(d / "health" / role),
        )
        return common

    def configure(self):
        say("Membuat konfigurasi layanan Absensa...")
        for folder in (
            "config",
            "photos",
            "backups",
            "whatsapp",
            "caddy",
            "logs",
            "temp",
            "health",
            "recovery",
        ):
            (self.data / folder).mkdir(exist_ok=True)
            self.host("private", Path=self.data / folder)
        for role in (*APPLICATION, "maintenance", "postgres"):
            for parent in ("temp", "logs", "health"):
                folder = self.data / parent / role
                folder.mkdir(exist_ok=True)
                self.host("private", Path=folder)
        for parent, key in (
            ("photos", "photo_tree"),
            ("whatsapp", "whatsapp_tree"),
            ("caddy", "caddy_tree"),
        ):
            (self.data / parent / self.config[key]).mkdir(exist_ok=True)
        for role in (*APPLICATION, "maintenance"):
            path = self.data / "config" / f"{role}.json"
            write_json(path, self.environment(role))
            self.host("private", Path=path)
        atomic(self.data / "config/Caddyfile", caddyfile(self.config))
        atomic(self.data / "config/recovery.key", self.config["backup_key"] + "\n")
        self.host("private", Path=self.config_path)
        self.host("private", Path=self.data / "config/recovery.key")

    def register(self):
        say("Memasang layanan Absensa...")
        service_dir = self.root / "services"
        service_dir.mkdir(exist_ok=True)
        # Existing service names are only adopted if their binary belongs to this root.
        for role, name in SERVICES.items():
            if self.exists(role):
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    "SYSTEM\\CurrentControlSet\\Services\\" + name,
                ) as key:
                    binary = winreg.QueryValueEx(key, "ImagePath")[0]
                if not binary.casefold().startswith(
                    '"' + str(self.root).casefold() + "\\"
                ):
                    raise OperationError("Nama layanan dipakai instalasi lain: " + name)
            if role == "postgres":
                if not self.exists(role):
                    self.run(
                        [
                            self.release / "postgres/bin/pg_ctl.exe",
                            "register",
                            "-N",
                            name,
                            "-D",
                            self.data / "postgres",
                            "-S",
                            "demand",
                        ]
                    )
                else:
                    command = subprocess.list2cmdline(
                        [
                            str(self.release / "postgres/bin/pg_ctl.exe"),
                            "runservice",
                            "-N",
                            name,
                            "-D",
                            str(self.data / "postgres"),
                            "-w",
                        ]
                    )
                    self.sc("config", name, "binPath=", command)
                self.sc(
                    "failure",
                    name,
                    "reset=",
                    "86400",
                    "actions=",
                    "restart/15000/restart/30000/restart/60000",
                )
            else:
                executable = service_dir / (name + ".exe")
                # Services are stopped before replacing the wrapper during maintenance.
                shutil.copy2(self.release / "winsw.exe", executable)
                xml = service_xml(role, self.release, self.data)
                atomic(executable.with_suffix(".xml"), xml)
                if self.exists(role):
                    # Pinned WinSW 2.12 has no refresh command. It reads the new
                    # XML on start; update SCM fields in place without deleting
                    # the service, its SID or its service-specific permissions.
                    definition = ET.fromstring(xml)
                    self.sc(
                        "config",
                        name,
                        "binPath=",
                        subprocess.list2cmdline([str(executable)]),
                        "start=",
                        "demand",
                        "depend=",
                        "/".join(node.text for node in definition.findall("depend")),
                        "DisplayName=",
                        definition.findtext("name"),
                    )
                    self.sc("description", name, definition.findtext("description"))
                else:
                    self.run([executable, "install"])
            self.host("service", Name=name)
            self.host("grant", Path=self.root, Name=name)
            self.host("grant", Path=self.data, Name=name, Rights="Traverse")
            self.host(
                "grant", Path=self.data / "logs" / role, Name=name, Rights="Modify"
            )
            for folder in ("temp", "health"):
                self.host(
                    "grant", Path=self.data / folder / role, Name=name, Rights="Modify"
                )
            if role != "postgres":
                self.host(
                    "grant",
                    Path=self.data / "config" / f"{role}.json",
                    Name=name,
                    Rights="Read",
                )
        for role, folder, rights in (
            ("postgres", "postgres", "Modify"),
            ("web", "photos", "Modify"),
            ("web", "backups", "ReadAndExecute"),
            ("backup", "photos", "ReadAndExecute"),
            ("backup", "backups", "Modify"),
            ("whatsapp", "whatsapp", "Modify"),
            ("caddy", "caddy", "Modify"),
            ("caddy", "config/Caddyfile", "Read"),
        ):
            self.host(
                "grant", Path=self.data / folder, Name=SERVICES[role], Rights=rights
            )
        self.set_start(False)
        report = self.host(
            "firewall",
            Path=self.release / "caddy/caddy.exe",
            Port=self.config["https_port"],
        )
        say(report.stdout.strip())

    def pg(self, tool, *args, database="postgres", check=True, input=None):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("PG"):
                del env[key]
        env.update(
            PGHOST="127.0.0.1",
            PGPORT=str(self.config["pg_port"]),
            PGUSER="absensa_owner",
            PGPASSWORD=self.config["pg_password"],
            PGDATABASE=database,
            PGCONNECT_TIMEOUT="10",
        )
        return self.run(
            [self.release / "postgres/bin" / (tool + ".exe"), *args],
            env=env,
            check=check,
            input=input,
            timeout=3900,
        )

    def initialize_database(self):
        say("Memasang PostgreSQL...")
        pgdata = self.data / "postgres"
        if not (pgdata / "PG_VERSION").exists():
            if self.state.get("initialized") or (
                pgdata.exists() and any(pgdata.iterdir())
            ):
                raise OperationError(
                    "Direktori PostgreSQL tidak kosong tetapi belum lengkap. Data dipertahankan; periksa log initdb sebelum pemulihan."
                )
            pgdata.mkdir(exist_ok=True)
            self.host("private", Path=pgdata)
            password_file = self.data / "config/initdb.password"
            atomic(password_file, self.config["pg_password"] + "\n")
            # PostgreSQL disables the Administrators SID before re-executing
            # initdb. Its restricted token needs explicit, temporary user ACEs.
            grants = []
            try:
                for path, rights in (
                    (self.root, "ReadAndExecute"),
                    (self.data, "Traverse"),
                    (self.data / "config", "Traverse"),
                    (pgdata, "Modify"),
                    (password_file, "Read"),
                ):
                    self.host("grant-installer", Path=path, Rights=rights)
                    grants.append((path, rights))
                self.run(
                    [
                        self.release / "postgres/bin/initdb.exe",
                        "-D",
                        pgdata,
                        "-U",
                        "absensa_owner",
                        "--pwfile",
                        password_file,
                        "--auth=scram-sha-256",
                        "--encoding=UTF8",
                        "--locale=C",
                    ]
                )
            finally:
                try:
                    for path, rights in reversed(grants):
                        self.host("revoke-installer", Path=path, Rights=rights)
                finally:
                    password_file.unlink(missing_ok=True)
        if (pgdata / "PG_VERSION").read_text().strip() != "18":
            raise OperationError(
                "Upgrade mayor PostgreSQL memerlukan migrasi tersendiri."
            )
        # Only our cluster; no global PostgreSQL or registry settings are changed.
        atomic(
            pgdata / "postgresql.auto.conf",
            f"listen_addresses = '127.0.0.1'\nport = {self.config['pg_port']}\npassword_encryption = 'scram-sha-256'\nlogging_collector = on\nlog_directory = '{(self.data / 'logs/postgres').as_posix()}'\nlog_filename = 'postgresql-%a.log'\nlog_truncate_on_rotation = on\nlog_rotation_age = '1d'\n",
        )

    def wait_database(self):
        for _ in range(60):
            if not self.pg("pg_isready", "-q", check=False).returncode:
                return
            time.sleep(1)
        raise OperationError("PostgreSQL belum siap. Periksa logs/postgres.")

    def create_database(self):
        self.start_services(("postgres",))
        self.wait_database()
        exists = self.pg(
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "SELECT 1 FROM pg_roles WHERE rolname='absensa'",
        ).stdout.strip()
        if not exists:
            # Password is hex from secrets.token_hex; SQL goes over stdin, not argv/logs.
            self.pg(
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                input=f"CREATE ROLE absensa LOGIN PASSWORD '{self.config['db_password']}' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n",
            )
        exists = self.pg(
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f"SELECT 1 FROM pg_database WHERE datname='{self.config['database']}'",
        ).stdout.strip()
        if not exists:
            if self.state.get("initialized"):
                raise OperationError(
                    "Database sekolah hilang. Pemulihan diperlukan; tidak membuat database kosong."
                )
            self.pg(
                "createdb",
                "--owner=absensa",
                "--encoding=UTF8",
                "--template=template0",
                self.config["database"],
            )

    def app(self, module, *args, input=None):
        return self.run(
            [
                self.python,
                self.release / "runtime.py",
                "--data",
                self.data,
                "--role",
                "maintenance",
                module,
                *args,
            ],
            input=input,
            timeout=3900,
        )

    def migrate(self):
        say("Menjalankan migrasi database...")
        self.app("alembic", "upgrade", "head")

    def admin(self, username=None):
        self.guard()
        if not self.state.get("initialized"):
            raise OperationError("Instalasi belum selesai. Jalankan repair sebelum membuat administrator.")
        self.start_services(("postgres",))
        self.wait_database()
        count = self.pg(
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "SELECT count(*) FROM admins",
            database=self.config["database"],
        ).stdout.strip()
        if count != "0":
            say("Akun administrator yang ada dipertahankan.")
            return
        username = (
            username
            or input("Nama pengguna administrator [admin]: ").strip()
            or "admin"
        )
        password = getpass.getpass("Sandi administrator (minimal 12 karakter): ")
        if len(password) < 12 or password != getpass.getpass("Ulangi sandi: "):
            raise OperationError(
                "Sandi terlalu pendek atau tidak sama. Jalankan admin kembali."
            )
        self.app(
            "scripts.create_admin",
            "--first-only",
            "--password-stdin",
            username,
            input=password + "\n",
        )
        say("Administrator siap.")

    @property
    def ca_path(self):
        return self.data / "caddy" / self.config["caddy_tree"] / "caddy/pki/authorities/local/root.crt"

    def health_failures(self):
        """One diagnostic pass; independent checks still run after a TLS failure."""
        failures = []
        c = self.config

        def check(component, action):
            try:
                action()
            except (OSError, ValueError, http.client.HTTPException, OperationError,
                    subprocess.SubprocessError) as exc:
                if isinstance(exc, ssl.SSLCertVerificationError):
                    reason = "certificate verification failed"
                elif isinstance(exc, ssl.SSLError):
                    reason = "TLS handshake failed"
                else:
                    reason = "failed"
                failures.append(self.redact(f"{component}: {reason}: {type(exc).__name__}: {exc}"))

        def https():
            context = ssl.create_default_context(
                cafile=str(self.ca_path) if c["tls"] == "internal" else None
            )
            status, body = https_health(c["host"], c["https_port"], context)
            if status != 200:
                raise OperationError(f"HTTPS /health returned unexpected status {status}")
            if not isinstance(body, dict) or body.get("ok") is not True:
                raise OperationError("HTTPS /health returned unhealthy body")

        def database():
            result = self.pg("psql", "-XAt", "-v", "ON_ERROR_STOP=1", "-c", "SELECT 1",
                             database=c["database"])
            if result.stdout.strip() != "1":
                raise OperationError("Database health check returned unexpected result")

        def service(role):
            if not self.running(role):
                raise OperationError(SERVICES[role] + " service stopped or not installed")

        def heartbeat(role):
            stamp = self.data / "health" / role / f"absensa-{role}.heartbeat"
            if not stamp.exists():
                raise OperationError(role + " heartbeat missing")
            age = time.time() - stamp.stat().st_mtime
            if age < -60 or age > (3900 if role == "backup" else 300):
                raise OperationError(f"{role} heartbeat stale or clock incorrect (age {age:.0f}s)")

        def whatsapp():
            bridge = http.client.HTTPConnection("127.0.0.1", c["bridge_port"], timeout=5)
            try:
                bridge.request("GET", "/health")
                response = bridge.getresponse()
                if response.status != 200:
                    raise OperationError(f"WhatsApp /health returned unexpected status {response.status}")
                body = json.loads(response.read())
                if not isinstance(body, dict) or body.get("ok") is not True:
                    raise OperationError("WhatsApp /health returned unhealthy body")
            finally:
                bridge.close()

        check(f"HTTPS {c['host']}:{c['https_port']}", https)
        check(f"Database 127.0.0.1:{c['pg_port']}", database)
        for role in SERVICES:
            check(SERVICES[role], lambda role=role: service(role))
        for role in ("scheduler", "backup"):
            check(role, lambda role=role: heartbeat(role))
        check(f"WhatsApp 127.0.0.1:{c['bridge_port']}", whatsapp)
        return failures

    def health(self, attempts=90, interval=2):
        say("Memeriksa kesehatan layanan...")
        started = time.monotonic()
        for attempt in range(1, attempts + 1):
            failures = self.health_failures()
            elapsed = time.monotonic() - started
            if not failures:
                if self.config["tls"] == "internal":
                    shutil.copyfile(self.ca_path, self.data / "root-ca.crt")
                    cert = ssl.PEM_cert_to_DER_cert(self.ca_path.read_text())
                    say(f"CA perangkat LAN: {self.data / 'root-ca.crt'}\nSHA-256: {hashlib.sha256(cert).hexdigest()}")
                self.diagnostic(f"Health OK after {elapsed:.1f}s ({attempt} attempts)")
                return
            phase = "FINAL FAILURE" if attempt == attempts else "RETRY"
            for failure in failures:
                say(self.diagnostic(f"Health {phase} {attempt}/{attempts}, {elapsed:.1f}s: {failure}"))
            if attempt < attempts:
                time.sleep(interval)
        raise OperationError(
            f"Pemeriksaan kesehatan gagal: {'; '.join(failures)}. "
            f"Periksa {self.data / 'logs/operations.log'}; jangan abaikan verifikasi TLS."
        )

    def status(self):
        say("Versi: " + (self.state["version"] if self.state else "belum terpasang"))
        say("Tahap: " + str((self.state or {}).get("transaction", "siap" if self.state else "belum lengkap")))
        say("Startup otomatis tercatat: " + str((self.state or {}).get("autostart", False)))
        if self.config:
            failures = self.health_failures()
            for failure in failures:
                say(failure)
            if not failures:
                say("Semua pemeriksaan kesehatan lulus.")
        else:
            say("Konfigurasi belum tersedia. Jalankan kembali installer.")
        log = self.data / "logs/operations.log"
        if log.exists():
            say("Diagnostik terakhir (termasuk kegagalan sebelum layanan dihentikan):")
            say(self.redact("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:])))

    def complete(self):
        # Keep a durable recovery journal until both health and SCM configuration
        # succeed. A failed/partial automatic-start change must remain repairable.
        self.state.setdefault("transaction", {"phase": "finalize"})
        self.state["autostart"] = False
        self.save()
        pending = self.state.copy()
        try:
            self.set_start(False)
            self.start_services()
            self.health()
            self.set_start(True)
            self.state["initialized"] = True
            self.state["autostart"] = True
            self.state.pop("transaction", None)
            self.save()
        except (Exception, KeyboardInterrupt):
            self.state = pending
            # Cleanup must not hide the original health/SCM failure. The journal
            # is still on disk if final publication failed.
            for cleanup in (lambda: self.set_start(False), lambda: self.stop(APPLICATION)):
                try:
                    cleanup()
                except Exception as exc:
                    self.diagnostic(f"Finalization cleanup failed: {type(exc).__name__}: {exc}")
            raise
        say(
            f"Administrator pertama (jika belum ada): & '{self.root / 'absensa.ps1'}' admin\n"
            f"Absensa berhasil dipasang: {self.state['version']}\nBuka: {self.environment('web')['CORS_ORIGIN']}/admin\nPengelolaan: & '{self.root / 'absensa.ps1'}' status\nLog: {self.data / 'logs'}"
        )

    def snapshot(self, resume=True):
        self.guard()
        active = [role for role in APPLICATION if self.running(role)]
        self.state["transaction"] = {
            "phase": "backup",
            "resume": active,
            "autostart": self.state.get("autostart", True),
        }
        self.save()
        self.set_start(False)
        result = None
        try:
            self.stop(APPLICATION)
            self.start_services(("postgres",))
            self.app("app.jobs.backups", "--once", "--manual")
            destination = (
                self.data
                / "backups"
                / (time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4) + ".absfull")
            )
            self.app("windows_archive", "snapshot", str(destination), str(self.data))
            result = destination
            say("Cadangan lengkap terenkripsi dan terverifikasi: " + str(result))
        finally:
            if resume or result is None:
                self.start_services(active)
                self.state.pop("transaction", None)
                self.save()
                self.set_start(self.state.get("autostart", True))
        return result

    def adopt_release(self, source):
        manifest = json.loads((source / "release.json").read_text())
        tag = manifest["version"]
        version(tag)
        if (
            manifest.get("platform") != "windows"
            or manifest.get("architecture") != "amd64"
            or manifest.get("format") != 1
            or manifest.get("postgres_major") != 18
        ):
            raise OperationError("Manifest Windows/arsitektur/PostgreSQL tidak cocok.")
        target = self.root / "releases" / tag
        if source.resolve() != target.resolve():
            if target.exists():
                # Do not overwrite a version in use, or silently reuse a partial copy.
                if self.state and self.state["version"] == tag:
                    raise OperationError("Versi ini sudah terpasang. Gunakan repair.")
                target.rename(
                    target.with_name(tag + ".partial-" + secrets.token_hex(4))
                )
            target.parent.mkdir(exist_ok=True)
            stage = target.with_name(tag + ".staging-" + secrets.token_hex(4))
            shutil.copytree(source, stage)
            stage.rename(target)
        return tag

    def update(self, source=None):
        self.guard()
        if source is None:
            with tempfile.TemporaryDirectory(
                prefix="release-", dir=self.data / "temp/maintenance"
            ) as temporary:
                target = Path(temporary)
                self.run(
                    [
                        os.path.join(
                            os.environ["SystemRoot"],
                            "System32/WindowsPowerShell/v1.0/powershell.exe",
                        ),
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        self.release / "install.ps1",
                        "-DownloadOnly",
                        str(target),
                    ]
                )
                return self.update(target / "release")
        manifest = json.loads((source / "release.json").read_text())
        tag = manifest["version"]
        if version(tag) <= version(self.state["version"]):
            say(
                "Versi stabil terbaru sudah terpasang. Penurunan versi otomatis ditolak."
            )
            return
        if (
            manifest.get("upgrade_from_major") != version(self.state["version"])[0]
            or manifest.get("postgres_major") != 18
        ):
            raise OperationError("Rilis memerlukan migrasi mayor tersendiri.")
        self.adopt_release(source)
        backup = self.snapshot(resume=False)
        self.state["transaction"] = {
            "phase": "migration",
            "previous": self.state["version"],
            "target": tag,
            "backup": str(backup),
        }
        self.state["version"] = tag
        self.save()  # No old application is permitted to start after this journal.
        self.stop()
        self.resume_target()

    def resume_target(self):
        # Use target-version logic and interpreter for migrations and service definitions.
        self.run(
            [
                self.python,
                self.release / "manage.py",
                "--root",
                self.root,
                "--data",
                self.data,
                "finish",
            ],
            timeout=3900,
        )
        self.state = read_json(self.state_path)

    def finish(self):
        self.storage_check()
        self.state.setdefault("transaction", {"phase": "repair"})
        self.state["autostart"] = False
        self.save()
        self.set_start(False)
        self.stop()
        self.configure()
        self.initialize_database()
        self.register()
        self.create_database()
        self.migrate()
        self.complete()

    def repair(self):
        transaction = self.state.get("transaction", {})
        if transaction.get("phase") == "restore":
            raise OperationError(
                "Pemulihan terhenti. Lihat recovery dan panduan pemulihan; database/foto lama tetap tersedia. Jangan menyalakan layanan sebelum memilih hasil pemulihan."
            )
        if transaction.get("phase") == "backup":
            self.start_services(transaction["resume"])
            self.state.pop("transaction")
            self.save()
            self.set_start(self.state.get("autostart", True))
            return
        if transaction.get("phase") == "restored":
            raise OperationError(
                "Pemulihan menunggu aktivasi. Hentikan instalasi sumber, lalu jalankan activate."
            )
        if self.release.resolve() != RELEASE.resolve():
            self.resume_target()
        else:
            self.finish()

    def restore(self, archive, key_file):
        self.guard()
        # Authenticate/unpack before downtime; only this operation's private workspace.
        key = base64.b64decode(key_file.read_text().strip(), validate=True)
        if len(key) != 32:
            raise OperationError("Kunci pemulihan harus 32 byte base64.")
        stage = self.data / "recovery" / ("restore_" + secrets.token_hex(6))
        stage.mkdir()
        self.app("windows_archive", "unpack", str(archive), str(stage), str(key_file))
        metadata = json.loads((stage / "database/manifest.json").read_text())
        if int(metadata["postgres_version"].split(".")[0]) > 18:
            raise OperationError(
                "Cadangan memakai PostgreSQL lebih baru dari server ini."
            )
        old = self.config.copy()
        restored = stage / "config/installation.json"
        if restored.exists():
            source_config = read_json(restored)
            source_state = read_json(stage / "config/state.json")
            if source_state["version"] != self.state["version"]:
                raise OperationError(
                    "Untuk arsip lengkap, pasang versi sumber dahulu: "
                    + source_state["version"]
                )
        if (
            input("Pemulihan menghentikan Absensa. Ketik PULIHKAN untuk melanjutkan: ")
            != "PULIHKAN"
        ):
            return
        backup = self.snapshot(resume=False)
        self.state["transaction"] = {
            "phase": "restore",
            "backup": str(backup),
            "stage": str(stage),
        }
        self.save()
        write_json(stage / "previous-config.json", old)
        name = "restore_" + secrets.token_hex(6)
        self.pg("createdb", "--owner=absensa", "--template=template0", name)
        # Restore as non-superuser, never execute a foreign dump with owner privileges.
        env = os.environ.copy()
        env.update(
            PGHOST="127.0.0.1",
            PGPORT=str(old["pg_port"]),
            PGUSER="absensa",
            PGPASSWORD=old["db_password"],
            PGDATABASE=name,
        )
        self.run(
            [
                self.release / "postgres/bin/pg_restore.exe",
                "--no-password",
                "--no-owner",
                "--no-privileges",
                "--single-transaction",
                "--exit-on-error",
                "--dbname",
                name,
                stage / "database/database.dump",
            ],
            env=env,
            timeout=3900,
        )
        shutil.copytree(stage / "database/photos", self.data / "photos" / name)
        self.config.update(database=name, photo_tree=name)
        if restored.exists():
            self.config.update(
                timezone=source_config["timezone"],
                backup_key=source_config["backup_key"],
                bridge_token=source_config["bridge_token"],
            )
            for folder, field in (
                ("whatsapp", "whatsapp_tree"),
                ("caddy", "caddy_tree"),
            ):
                if (stage / folder).is_dir():
                    shutil.copytree(stage / folder, self.data / folder / name)
                    self.config[field] = name
        write_json(self.config_path, self.config)
        self.configure()
        self.register()
        self.start_services(("postgres",))
        self.migrate()
        # Keep messaging stopped until explicit activation on recovered school data.
        self.state["transaction"] = {
            "phase": "restored",
            "backup": str(backup),
            "stage": str(stage),
        }
        self.save()
        say(
            "Database dan foto dipulihkan ke penyimpanan baru. Data sebelumnya dipertahankan. Hentikan instalasi sumber lalu jalankan activate."
        )

    def uninstall(self):
        if (
            input(
                "Hapus layanan/binary Absensa? Data tetap disimpan. Ketik HAPUS APLIKASI: "
            )
            != "HAPUS APLIKASI"
        ):
            return
        self.set_start(False)
        self.stop()
        for role in reversed(tuple(SERVICES)):
            if self.exists(role):
                self.sc("delete", SERVICES[role])
        self.host("unfirewall")
        # The launcher removes binaries after this interpreter exits.
        self.state["uninstalled"] = True
        self.state["autostart"] = False
        self.save()
        say(
            f"Layanan dan aturan firewall dihapus. Launcher akan menghapus hanya folder binary: {self.root}\nData, konfigurasi, foto, cadangan dan kunci tetap di {self.data}. Jangan hapus direktori data."
        )


def install(obj, source, args):
    if obj.state:
        say(
            "Instalasi ditemukan. Memperbaiki versi tersimpan; gunakan update untuk versi baru."
        )
        manifest = json.loads((source / "release.json").read_text())
        if manifest["version"] != obj.state["version"]:
            raise OperationError(
                "Perbaikan memerlukan artefak versi tersimpan; gunakan update untuk versi lain."
            )
        if not (obj.release / "manage.py").is_file():
            obj.set_start(False)
            obj.stop()
            if obj.release.exists():
                obj.release.rename(
                    obj.release.with_name(
                        obj.release.name + ".damaged-" + secrets.token_hex(4)
                    )
                )
            obj.adopt_release(source)
        shutil.copyfile(source / "absensa.ps1", obj.root / "absensa.ps1")
        write_json(obj.root / "location.json", {"data": str(obj.data)})
        obj.state.pop("uninstalled", None)
        obj.save()
        obj.repair()
        if not args.no_admin:
            obj.admin()
        return
    if obj.config or (obj.data / "postgres").exists():
        raise OperationError(
            "Konfigurasi/data tanpa state ditemukan. Pulihkan state.json; rahasia tidak dibuat ulang."
        )
    if (
        min(shutil.disk_usage(obj.root).free, shutil.disk_usage(obj.data).free)
        < 10 * 1024**3
    ):
        raise OperationError(
            "Sediakan sedikitnya 10 GB kosong untuk runtime, data dan cadangan."
        )
    host = (
        args.hostname
        or input("Nama DNS atau IPv4 LAN tetap server (contoh 192.168.1.10): ").strip()
    )
    port = args.port or int(
        input("Port HTTPS [443, gunakan 8443 bila sudah dipakai]: ").strip() or "443"
    )
    mode = args.tls or (
        "cloudflare"
        if input("HTTPS: 1 CA lokal, 2 domain Cloudflare [1]: ").strip() == "2"
        else "internal"
    )
    token = (
        getpass.getpass("Token Cloudflare DNS zona sekolah: ")
        if mode == "cloudflare"
        else ""
    )
    zone = args.timezone
    if zone is None:
        selection = input("Zona waktu: 1 WIB, 2 WITA, 3 WIT [1]: ").strip() or "1"
        if selection not in ("1", "2", "3"):
            raise OperationError("Pilih zona waktu 1, 2, atau 3.")
        zone = ("Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura")[int(selection) - 1]
    config = new_config(host, port, zone, mode, token)
    for candidate in (
        port,
        config["pg_port"],
        config["web_port"],
        config["bridge_port"],
    ):
        with socket.socket() as sock:
            try:
                sock.bind(("0.0.0.0" if candidate == port else "127.0.0.1", candidate))
            except OSError as exc:
                raise OperationError(
                    f"Port TCP {candidate} sudah digunakan. Jangan hentikan aplikasi sekolah lain."
                ) from exc
    tag = obj.adopt_release(source)
    obj.config = config
    obj.state = {
        "format": 1,
        "version": tag,
        "root": str(obj.root),
        "data": str(obj.data),
        "initialized": False,
        "transaction": {"phase": "install"},
    }
    # Persist configuration and identity together before initdb; crashes fail closed.
    write_json(obj.config_path, config)
    shutil.copyfile(source / "absensa.ps1", obj.root / "absensa.ps1")
    write_json(obj.root / "location.json", {"data": str(obj.data)})
    obj.save()
    obj.finish()
    if not args.no_admin:
        obj.admin()
    say(f"Simpan kunci pemulihan secara terpisah: {obj.data / 'config/recovery.key'}")


def main():
    parser = argparse.ArgumentParser(description="Pengelolaan Absensa native Windows")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Absensa",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Absensa",
    )
    parser.add_argument("--source", type=Path, default=RELEASE)
    parser.add_argument("--hostname")
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--timezone", choices=("Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura")
    )
    parser.add_argument("--tls", choices=("internal", "cloudflare"))
    parser.add_argument(
        "--no-admin",
        action="store_true",
        help="Buat admin kemudian dengan perintah admin",
    )
    parser.add_argument(
        "action",
        choices=(
            "install",
            "status",
            "start",
            "stop",
            "restart",
            "logs",
            "backup",
            "restore",
            "update",
            "admin",
            "repair",
            "activate",
            "uninstall",
            "finish",
        ),
    )
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    sys.path.insert(0, str(RELEASE / "web"))
    if os.name != "nt":
        raise SystemExit("Pengelola ini hanya untuk Windows Server amd64.")
    # Bootstrap has created/restricted both roots. Installed commands never create missing data.
    try:
        obj = Installation(args.root, args.data)
        obj.host("platform")
        from process_job import contain_current_process

        contain_current_process()
        # finish is a child of the manager holding the lock, and is never public.
        # The parent keeps its kernel lock while synchronously waiting for this child.
        lock = (
            contextlib.nullcontext()
            if args.action == "finish"
            and os.environ.get("ABSENSA_PARENT_OPERATION") == str(os.getppid())
            else operation_lock(obj.data)
        )
        with lock:
            os.environ["ABSENSA_PARENT_OPERATION"] = str(os.getpid())
            if args.action == "install":
                install(obj, args.source, args)
            elif args.action == "status":
                obj.status()
            elif args.action == "finish":
                obj.finish()
            elif args.action == "repair":
                obj.repair()
            elif args.action == "stop":
                obj.set_start(False)
                obj.stop()
                obj.state["autostart"] = False
                obj.save()
            elif args.action in ("start", "restart"):
                obj.guard()
                if args.action == "restart":
                    obj.stop()
                obj.complete()
            elif args.action == "backup":
                obj.snapshot()
            elif args.action == "update":
                obj.update()
            elif args.action == "restore":
                if len(args.arguments) != 2:
                    raise OperationError(
                        "Gunakan restore C:\\cadangan.absfull C:\\recovery.key (atau .absbackup)."
                    )
                obj.restore(*map(Path, args.arguments))
            elif args.action == "activate":
                if obj.state.get("transaction", {}).get("phase") != "restored":
                    raise OperationError(
                        "Tidak ada hasil pemulihan yang menunggu aktivasi."
                    )
                if (
                    input("Instalasi sumber sudah dihentikan? Ketik AKTIFKAN: ")
                    == "AKTIFKAN"
                ):
                    obj.complete()
            elif args.action == "admin":
                obj.admin()
            elif args.action == "logs":
                role = args.arguments[0] if args.arguments else "web"
                if role not in SERVICES:
                    raise OperationError(
                        "Pilih postgres, web, scheduler, backup, whatsapp, atau caddy."
                    )
                for path in (obj.data / "logs" / role).glob("*.log"):
                    say(str(path))
                    say(
                        "\n".join(
                            path.read_text(
                                encoding="utf-8", errors="replace"
                            ).splitlines()[-80:]
                        )
                    )
            elif args.action == "uninstall":
                obj.uninstall()
    except (
        OperationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        # Deliberately avoid arbitrary exception messages which may include credentials.
        detail = (
            str(exc)
            if isinstance(exc, OperationError)
            else "Periksa konfigurasi, ruang disk, izin dan log layanan."
        )
        raise SystemExit(
            f"Operasi Absensa dihentikan. {detail}\nLog: {args.data / 'logs'}\nData dipertahankan. Jalankan status atau repair; untuk kegagalan migrasi pulihkan cadangan sebelum pembaruan."
        ) from None


if __name__ == "__main__":
    main()
