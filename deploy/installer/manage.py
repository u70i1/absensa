"""Absensa installation manager. Standard-library Python; the app runs in Docker."""

import argparse
import base64
import fcntl
import getpass
import ipaddress
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from release import TAG, InstallError, fetch

SERVICES = ("web", "scheduler", "backup", "whatsapp", "caddy")
TIMEZONES = ("Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura")
ROOT = (
    Path(__file__).resolve().parents[2]
    if Path(__file__).resolve().parent.name == "installer"
    else None
)


def say(message):
    print(message, flush=True)


def ask(message, default=""):
    try:
        with open("/dev/tty", "r+") as tty:
            tty.write(f"{message}" + (f" [{default}]" if default else "") + ": ")
            tty.flush()
            value = tty.readline()
            if not value:
                raise InstallError(
                    "Terminal ditutup. Konfigurasi yang sudah ada tetap disimpan."
                )
            return value.strip() or default
    except OSError as exc:
        raise InstallError(
            "Buka terminal interaktif untuk melanjutkan instalasi."
        ) from exc


def yes(message, default=False):
    while True:
        value = ask(message + " (ya/tidak)", "ya" if default else "tidak").lower()
        if value in {"ya", "y"}:
            return True
        if value in {"tidak", "t", "n"}:
            return False
        say("Ketik ya atau tidak.")


def run(args, *, data=None, check=True, timeout=900, env_remove=()):
    # Environment variables must never silently override saved Compose settings.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("COMPOSE_", "DOCKER_")) and k not in env_remove
    }
    try:
        result = subprocess.run(
            args, input=data, capture_output=True, text=True, env=env, timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError(
            "Perintah tidak dapat selesai. Periksa dependensi, koneksi, dan status layanan."
        ) from exc
    if check and result.returncode:
        # Never log raw Docker/SQL/validation errors: they can contain secrets.
        if "all predefined address pools have been fully subnetted" in result.stderr:
            raise InstallError(
                "Alamat subnet jaringan Docker sudah habis. Minta petugas IT meninjau jaringan Docker yang tidak digunakan atau menyediakan server lain. Jangan menghapus jaringan aplikasi sekolah. Data dipertahankan; setelah kapasitas tersedia, jalankan perbaiki, atau ulangi pemulihan ke direktori baru jika yang gagal adalah pemulihan."
            )
        raise InstallError(
            "Operasi gagal. Data dipertahankan. Gunakan perintah status atau log untuk memeriksa layanan."
        )
    return result


def atomic(path, text, mode=0o600):
    path = Path(path)
    temporary = path.with_name(path.name + ".new")
    with temporary.open("w") as output:
        os.chmod(temporary, mode)
        output.write(text)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path):
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or path.resolve() != path:
        raise InstallError("Gunakan direktori nyata, bukan tautan simbolis.")
    # Restriction simplifies Compose, cron and recovery without shell interpolation.
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)) or ".." in path.parts:
        raise InstallError("Gunakan lokasi absolut tanpa spasi atau karakter khusus.")
    return path


def env_read(path):
    values = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z_]+", key) or key in values:
            raise InstallError(
                "Konfigurasi tidak sah; jangan buat ulang sandi database."
            )
        values[key] = value
    return values


def env_write(path, values):
    for key, value in values.items():
        if any(c in str(value) for c in "\r\n$#'\"\\"):
            raise InstallError(
                f"Nilai konfigurasi {key} mengandung karakter yang tidak didukung."
            )
    atomic(path, "".join(f"{key}={value}\n" for key, value in values.items()))


def version_tuple(value):
    if not TAG.fullmatch(value):
        raise InstallError("Versi tersimpan tidak sah.")
    return tuple(map(int, value[1:].split(".")))


def host_check(directory, *, resources=True):
    if (
        sys.version_info < (3, 10)
        or sys.platform != "linux"
        or platform.machine() != "x86_64"
    ):
        raise InstallError(
            "Diperlukan Linux amd64 dan Python 3.10+. Gunakan Ubuntu 24.04 LTS 64-bit, termasuk VM Linux di Windows Server."
        )
    if any(
        os.environ.get(k)
        for k in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "COMPOSE_FILE",
            "COMPOSE_PROJECT_NAME",
        )
    ):
        raise InstallError(
            "Hapus DOCKER_HOST/DOCKER_CONTEXT/COMPOSE_FILE/COMPOSE_PROJECT_NAME dari terminal. Hanya Docker lokal didukung."
        )
    context = json.loads(run(["docker", "context", "inspect"]).stdout)[0]
    endpoint = context.get("Endpoints", {}).get("docker", {}).get("Host", "")
    if not endpoint.startswith("unix://"):
        raise InstallError(
            "Konteks Docker harus memakai soket lokal Linux, bukan server jarak jauh."
        )
    info = json.loads(run(["docker", "info", "--format", "{{json .}}"]).stdout)
    if info.get("OSType") != "linux" or info.get("Architecture") not in {
        "x86_64",
        "amd64",
    }:
        raise InstallError("Docker harus menjalankan container Linux amd64.")
    compose_version = (
        run(["docker", "compose", "version", "--short"]).stdout.strip().lstrip("v")
    )
    parts = re.match(r"(\d+)\.(\d+)", compose_version)
    if not parts or tuple(map(int, parts.groups())) < (2, 24):
        raise InstallError("Diperlukan Docker Compose 2.24 atau lebih baru.")
    engine = re.match(r"(\d+)", info.get("ServerVersion", "0"))
    if not engine or int(engine[1]) < 24:
        raise InstallError("Diperlukan Docker Engine 24 atau lebih baru.")
    if not resources:
        return
    existing = directory
    while not existing.exists():
        existing = existing.parent
    if shutil.disk_usage(existing).free < 10 * 1024**3:
        raise InstallError(
            "Ruang kosong kurang dari 10 GB. Sediakan ruang untuk image, data, dan cadangan."
        )
    if info.get("MemTotal", 0) < 3500 * 1024**2:
        raise InstallError("Docker membutuhkan sedikitnya 4 GB RAM; 8 GB disarankan.")
    memory = dict(
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
    )
    if int(memory.get("MemAvailable", "0 kB").split()[0]) < 2 * 1024**2:
        raise InstallError(
            "RAM tersedia kurang dari 2 GB. Jangan mengganggu aplikasi lain; tambah kapasitas atau gunakan server lain."
        )
    say(
        "Docker lokal dan Compose tersedia. Layanan sekolah yang sudah ada akan dipertahankan."
    )


def hostname(value):
    try:
        address = ipaddress.IPv4Address(value)
        if address.is_unspecified or address.is_multicast or address.is_loopback:
            raise ValueError
        return str(address)
    except ipaddress.AddressValueError:
        if (
            len(value) > 253
            or "." not in value
            or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in value.split(".")
            )
        ):
            raise InstallError(
                "Isi nama domain huruf kecil atau alamat IPv4 LAN server tanpa https:// dan tanpa garis miring."
            )
        return value
    except ValueError as exc:
        raise InstallError(
            "Gunakan alamat LAN server yang dapat diakses perangkat sekolah."
        ) from exc


def choose_port(bind="0.0.0.0", default=443):
    while True:
        value = ask("Port HTTPS untuk Absensa", str(default))
        if value.isdecimal() and 1 <= int(value) <= 65535:
            # Inspect Docker too: some hosts disable docker-proxy, so bind() alone misses DNAT.
            ports = run(["docker", "ps", "--format", "{{.Ports}}"]).stdout
            if re.search(rf":{value}->", ports):
                say("Port digunakan container lain. Pilih misalnya 8443.")
                continue
            with socket.socket() as probe:
                try:
                    probe.bind((bind, int(value)))
                    return int(value)
                except OSError:
                    say(
                        "Port tidak tersedia atau izin tidak cukup. Pilih misalnya 8443."
                    )
        else:
            say("Isi angka 1–65535.")


def caddyfile(config):
    tls = (
        "tls internal"
        if config["TLS_MODE"] != "cloudflare"
        else "tls {\n        dns cloudflare {env.CF_API_TOKEN}\n        resolvers 1.1.1.1 1.0.0.1\n    }"
    )
    return (
        "{\n    auto_https disable_redirects\n    admin off\n}\n"
        + f"https://{config['HOSTNAME']}:443 {{\n    {tls}\n    header Strict-Transport-Security max-age=31536000\n    reverse_proxy unix//run/absensa/web.sock\n}}\n"
    )


class Installation:
    def __init__(self, root):
        self.root = private_directory(root)
        self.state_path = self.root / "state.json"
        self.config_path = self.root / "production.env"
        self.state = json.loads(self.state_path.read_text())
        self.config = env_read(self.config_path)
        if self.state.get("format") != 1 or not re.fullmatch(
            r"absensa-[a-f0-9]{12}", self.state.get("project", "")
        ):
            raise InstallError(
                "Identitas instalasi tidak sah. Pulihkan konfigurasi dari cadangan."
            )
        version_tuple(self.state["version"])
        if self.config.get("INSTALL_DIR") != str(self.root):
            raise InstallError(
                "Direktori instalasi berpindah. Gunakan pemulihan ke direktori baru."
            )
        for key in ("POSTGRES_PASSWORD", "WHATSAPP_BRIDGE_TOKEN"):
            if not re.fullmatch(r"[a-f0-9]{64}", self.config.get(key, "")):
                raise InstallError(
                    "Rahasia instalasi tidak sah; pulihkan production.env tanpa mengganti sandi database."
                )
        if (
            len(
                base64.b64decode(
                    self.config.get("BACKUP_ENCRYPTION_KEY", ""), validate=True
                )
            )
            != 32
        ):
            raise InstallError("Kunci cadangan tidak sah.")
        if (
            not re.fullmatch(r"[0-9]{1,5}", self.config.get("HTTPS_PORT", ""))
            or not 1 <= int(self.config["HTTPS_PORT"]) <= 65535
        ):
            raise InstallError("Port HTTPS dalam konfigurasi tidak sah.")
        if self.config.get("TLS_MODE") not in {"internal", "cloudflare", "proxy"}:
            raise InstallError("Mode HTTPS tidak sah.")
        ipaddress.IPv4Address(self.config["BIND_IP"])
        if (
            not self.config.get("FULL_BACKUP_KEEP", "").isdigit()
            or not 1 <= int(self.config["FULL_BACKUP_KEEP"]) <= 365
        ):
            raise InstallError("Retensi cadangan lengkap harus 1–365.")
        if self.config.get("TIMEZONE") not in TIMEZONES:
            raise InstallError("Zona waktu tidak sah.")
        hostname(self.config["HOSTNAME"])
        private_directory(self.config["BACKUP_DIR"])

    @property
    def release(self):
        return self.root / "releases" / self.state["version"]

    def save(self):
        atomic(self.state_path, json.dumps(self.state, indent=2) + "\n")

    def compose(self, *args, **kwargs):
        kwargs["env_remove"] = set(self.config) | {
            name + "_IMAGE"
            for name in ("WEB", "BACKUP", "WHATSAPP", "CADDY", "POSTGRES")
        }
        return run(
            [
                "docker",
                "compose",
                "--project-name",
                self.state["project"],
                "--project-directory",
                str(self.root),
                "--env-file",
                str(self.config_path),
                "-f",
                str(self.release / "compose.yml"),
                *args,
            ],
            **kwargs,
        )

    def write_runtime(self):
        manifest = json.loads((self.release / "release.json").read_text())
        if manifest["version"] != self.state["version"] or manifest["format"] != 1:
            raise InstallError("Manifest tidak cocok.")
        for name, image in manifest["images"].items():
            if not re.fullmatch(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}", image):
                raise InstallError("Image rilis harus dikunci dengan digest.")
            self.config[f"{name.upper()}_IMAGE"] = image
        env_write(self.config_path, self.config)
        atomic(self.root / "Caddyfile", caddyfile(self.config))
        self.compose("config", "--quiet")

    def diagnose(self, message):
        # Only our labels, never commands/env or raw exception strings.
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with (self.root / "operations.log").open("a") as output:
            output.write(f"{stamp} {message}\n")

    def running(self):
        return self.compose("ps", "--services", "--status", "running").stdout.split()

    def ensure_storage(self):
        if not self.state.get("initialized"):
            return
        volumes = [
            f"{self.state['project']}_{name}"
            for name in ("pgdata", "photos", "whatsapp_auth", "caddy_data")
        ]
        if run(["docker", "volume", "inspect", *volumes], check=False).returncode:
            raise InstallError(
                "Volume data instalasi tidak lengkap. Operasi dihentikan agar database kosong tidak menggantikan data sekolah. Periksa penyimpanan Docker atau pulihkan cadangan ke proyek baru."
            )

    def guard(self):
        if not Path(self.config["BACKUP_DIR"]).is_dir():
            raise InstallError(
                "Media cadangan tidak terpasang. Sambungkan kembali sebelum menjalankan layanan."
            )
        if self.state.get("restored_isolated"):
            raise InstallError(
                "Hasil pemulihan masih terisolasi. Jalankan aktifkan setelah instalasi lama dihentikan."
            )
        if self.state.get("transaction"):
            raise InstallError(
                "Operasi sebelumnya terhenti. Jalankan perbaiki; jangan menyalakan versi lama setelah migrasi."
            )
        self.ensure_storage()

    def pull(self):
        say(
            "Mengunduh image sesuai digest rilis; proses dapat memerlukan beberapa menit…"
        )
        self.compose("--profile", "maintenance", "pull", timeout=1800)

    def migrate(self):
        self.ensure_storage()
        self.ensure_no_orphans()
        self.prepare_backup_directory()
        say("Menjalankan migrasi database…")
        self.compose("up", "-d", "--wait", "--wait-timeout", "120", "db")
        self.compose("run", "--rm", "--no-deps", "migrate", timeout=900)
        self.prepare_socket()

    def prepare_backup_directory(self):
        if self.state.get("initialized"):
            return
        # A failed initial pull may leave this approved directory owned by the
        # host account. Repair must finish setup before the worker writes here.
        self.compose(
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0",
            "backup",
            "python",
            "-c",
            "import os; os.chown('/app/backups',10001,10001); os.chmod('/app/backups',0o700)",
        )

    def prepare_socket(self):
        self.compose(
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0",
            "web",
            "python",
            "-c",
            "import os; os.chown('/run/absensa',10001,10001); os.chmod('/run/absensa',0o755)",
        )

    def initialize_admin(self):
        count = self.compose(
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "absensa",
            "-d",
            "absensa",
            "-Atc",
            "SELECT count(*) FROM admins",
        ).stdout.strip()
        if count != "0":
            return
        if not yes("Buat akun administrator pertama sekarang?", True):
            say(
                "Sebelum digunakan, jalankan ./absensa admin untuk membuat administrator."
            )
            return
        while True:
            username = ask("Nama pengguna administrator", "admin").casefold()
            if not 1 <= len(username) <= 100:
                say("Nama harus berisi 1–100 karakter.")
                continue
            password = getpass.getpass("Sandi administrator (minimal 12 karakter): ")
            if not 12 <= len(password) <= 1024 or "\n" in password or "\r" in password:
                say("Gunakan 12–1024 karakter tanpa baris baru.")
                continue
            if password != getpass.getpass("Ulangi sandi: "):
                say("Sandi tidak sama.")
                continue
            self.compose(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "web",
                "python",
                "-m",
                "scripts.create_admin",
                "--first-only",
                "--password-stdin",
                username,
                data=password + "\n",
            )
            say("Administrator siap. Akun yang sudah ada tidak diubah.")
            return

    def check_https(self):
        host, port = self.config["HOSTNAME"], self.config["HTTPS_PORT"]
        ca = self.root / "root-ca.crt"
        if self.config["TLS_MODE"] != "cloudflare":
            for attempt in range(30):
                result = self.compose(
                    "cp",
                    "caddy:/data/caddy/pki/authorities/local/root.crt",
                    str(ca),
                    check=False,
                )
                if result.returncode == 0:
                    break
                time.sleep(2)
            if not ca.exists():
                raise InstallError("CA lokal belum tersedia. Periksa log Caddy.")
            ca.chmod(0o644)
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--noproxy",
            "*",
            "--connect-timeout",
            "5",
            "--max-time",
            "10",
            "--resolve",
            f"{host}:{port}:{self.config['BIND_IP'] if self.config['BIND_IP'] != '0.0.0.0' else '127.0.0.1'}",
        ]
        if self.config["TLS_MODE"] != "cloudflare":
            command.extend(["--cacert", str(ca)])
        for attempt in range(60):
            if attempt % 10 == 0:
                say("Menunggu sertifikat dan koneksi HTTPS terverifikasi…")
            result = run([*command, f"https://{host}:{port}/health"], check=False)
            if result.returncode == 0 and json.loads(result.stdout).get("ok") is True:
                break
            time.sleep(3)
        else:
            raise InstallError(
                "HTTPS belum siap. Periksa sertifikat, token DNS, jam server dan log Caddy. Aplikasi tidak dinyatakan siap."
            )
        if self.config["TLS_MODE"] == "proxy":
            result = run(
                [
                    "curl",
                    "--silent",
                    "--fail",
                    "--noproxy",
                    "*",
                    "--max-time",
                    "15",
                    self.config["PUBLIC_URL"] + "/health",
                ],
                check=False,
            )
            if result.returncode or json.loads(result.stdout).get("ok") is not True:
                raise InstallError(
                    "HTTPS internal siap; reverse proxy luar belum terverifikasi. Ikuti petunjuk proxy di panduan, kemudian jalankan periksa."
                )
        elif not re.fullmatch(r"[0-9.]+", host):
            try:
                socket.getaddrinfo(host, int(port))
            except OSError:
                say(
                    "DNS sekolah belum mengenali nama ini. Minta petugas IT mengarahkan nama tersebut ke IP LAN server."
                )
        say("HTTPS dan koneksi database berhasil diperiksa dari server.")
        if self.config["TLS_MODE"] != "cloudflare":
            fingerprint = run(
                ["openssl", "x509", "-in", str(ca), "-noout", "-fingerprint", "-sha256"]
            ).stdout.strip()
            say(
                f"Sertifikat publik untuk perangkat sekolah: {ca}\n{fingerprint}\nPasang CA ini pada setiap perangkat melalui pengaturan sertifikat; petunjuk ada di panduan."
            )

    def start(self, admin=False):
        self.guard()
        self.write_runtime()
        self.migrate()
        if admin:
            self.initialize_admin()
        say("Menyalakan layanan dan memeriksa kesiapan…")
        # Atomic Caddyfile replacement changes its inode. Recreate the bind mount.
        self.compose("up", "-d", "--force-recreate", "caddy")
        self.compose(
            "up", "-d", "--wait", "--wait-timeout", "240", *SERVICES, timeout=300
        )
        self.check_https()
        self.state["initialized"] = True
        self.save()
        say(
            f"Alamat Absensa: {self.config['PUBLIC_URL']}/admin\nUji juga dari perangkat Wi-Fi sekolah. Hubungkan WhatsApp melalui menu WhatsApp dan pindai kode QR."
        )

    def snapshot(self, resume=True):
        self.guard()
        self.ensure_no_orphans()
        if not self.state.get("initialized"):
            raise InstallError(
                "Jalankan instalasi sampai siap sebelum membuat cadangan lengkap."
            )
        active = [name for name in self.running() if name in SERVICES]
        self.state["transaction"] = {"phase": "backup", "resume": active}
        self.save()
        self.compose("stop", *SERVICES)
        result = None
        try:
            self.compose("up", "-d", "--wait", "db")
            self.compose(
                "run",
                "--rm",
                "--no-deps",
                "backup",
                "python",
                "-m",
                "app.jobs.backups",
                "--once",
                "--manual",
                timeout=3900,
            )
            snapshots = Path(self.config["BACKUP_DIR"]) / "full"
            # Created as application UID within the pre-authorized backup bind mount.
            self.compose(
                "run",
                "--rm",
                "--no-deps",
                "backup",
                "python",
                "-c",
                "from pathlib import Path; Path('/app/backups/full').mkdir(mode=0o700,exist_ok=True)",
            )
            name = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4) + ".absfull"
            with tempfile.TemporaryDirectory(
                prefix="snapshot-", dir=self.root
            ) as directory:
                stage = Path(directory)
                for file in ("production.env", "state.json", "Caddyfile"):
                    shutil.copy2(self.root / file, stage / file)
                shutil.copytree(self.release, stage / "release")
                # Private configuration, WA and CA are read-only; only this project's volumes.
                self.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--user",
                    "0",
                    "-v",
                    f"{stage}:/snapshot/config:ro",
                    "-v",
                    f"{self.state['project']}_whatsapp_auth:/snapshot/whatsapp:ro",
                    "-v",
                    f"{self.state['project']}_caddy_data:/snapshot/caddy:ro",
                    "backup",
                    "python",
                    "-m",
                    "app.jobs.deployment_archive",
                    "snapshot",
                    f"/app/backups/full/{name}",
                    timeout=3900,
                )
            result = snapshots / name
            say(f"Cadangan lengkap terenkripsi dan terverifikasi: {result}")
            # Rotation limited to generated files; authenticate before removal.
            self.compose(
                "run",
                "--rm",
                "--no-deps",
                "--user",
                "0",
                "backup",
                "python",
                "-c",
                "from pathlib import Path; from app.services.backup_crypto_service import verify_archive,encryption_key; import re; p=Path('/app/backups/full'); files=sorted(x for x in p.iterdir() if re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{8}\\.absfull',x.name) and not x.is_symlink()); valid=[]; key=encryption_key();\nfor x in files:\n try: verify_archive(x,key); valid.append(x)\n except Exception: pass\nfor x in valid[:-"
                + self.config["FULL_BACKUP_KEEP"]
                + "]: x.unlink()",
                timeout=3900,
            )
        finally:
            # No migrations were run, so exact previous services may safely resume.
            if (resume or result is None) and active:
                self.compose("start", *active)
            if resume or result is None:
                self.state.pop("transaction", None)
                self.save()
        return result

    def update(self):
        self.guard()
        with tempfile.TemporaryDirectory(prefix="release-", dir=self.root) as directory:
            target = fetch(directory)
            manifest = json.loads((target / "release.json").read_text())
            version = manifest["version"]
            if version_tuple(version) <= version_tuple(self.state["version"]):
                say(
                    "Versi stabil terbaru sudah terpasang; penurunan versi otomatis tidak diizinkan."
                )
                return
            if (
                manifest.get("upgrade_from_major")
                != version_tuple(self.state["version"])[0]
            ):
                raise InstallError(
                    "Rilis ini memerlukan prosedur migrasi khusus. Ikuti catatan rilis; data belum diubah."
                )
            if not yes(
                f"Perbarui {self.state['version']} ke {version}? Layanan berhenti sementara selama pencadangan dan migrasi"
            ):
                return
            destination = self.root / "releases" / version
            if destination.exists():
                destination.rename(
                    destination.with_name(
                        version + ".tersimpan-" + secrets.token_hex(4)
                    )
                )
            shutil.copytree(target, destination)
        # Validate target config and pull BEFORE stopping the old deployment.
        previous = self.state["version"]
        old_config = self.config.copy()
        try:
            self.state["version"] = version
            self.write_runtime()
            self.pull()
        finally:
            self.state["version"] = previous
            self.config = old_config
            self.write_runtime()
        backup = self.snapshot(resume=False)
        self.state["transaction"] = {
            "phase": "migration",
            "previous": previous,
            "target": version,
            "backup": str(backup),
        }
        self.save()  # Durable journal BEFORE any schema change; no blind downgrade.
        self.finish_update()

    def finish_update(self):
        transaction = self.state["transaction"]
        self.state["version"] = transaction["target"]
        self.save()
        self.write_runtime()
        self.migrate()
        self.compose("up", "-d", "--force-recreate", "caddy")
        self.compose(
            "up", "-d", "--wait", "--wait-timeout", "240", *SERVICES, timeout=300
        )
        self.check_https()
        self.state.pop("transaction")
        self.save()
        say(f"Pembaruan berhasil: {self.state['version']}.")

    def ensure_no_orphans(self):
        result = run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.compose.project={self.state['project']}",
                "--filter",
                "label=com.docker.compose.oneoff=True",
                "--format",
                "{{.ID}}",
            ]
        )
        if result.stdout.strip():
            raise InstallError(
                "Container pemeliharaan sebelumnya masih berjalan. Tunggu sampai selesai dan periksa status sebelum mencoba perbaiki lagi."
            )

    def activate(self):
        if not self.state.get("restored_isolated") or self.state.get("transaction"):
            raise InstallError(
                "Aktifkan hanya digunakan setelah pemulihan terisolasi berhasil."
            )
        if not yes(
            "Instalasi lama sudah dihentikan, termasuk WhatsApp dan penjadwalnya? Lanjutkan pengaktifan hasil pemulihan"
        ):
            return
        self.config["HOSTNAME"] = hostname(
            ask("Domain atau IP LAN server tujuan", self.config["HOSTNAME"])
        )
        mode = ask(
            "HTTPS: 1) CA lokal, 2) Domain Cloudflare, 3) Reverse proxy yang sudah ada",
            "1",
        )
        if mode not in {"1", "2", "3"}:
            raise InstallError("Pilih 1, 2, atau 3.")
        if mode != "1" and re.fullmatch(r"[0-9.]+", self.config["HOSTNAME"]):
            raise InstallError("Mode domain/proxy memerlukan nama domain.")
        self.config["TLS_MODE"] = {"1": "internal", "2": "cloudflare", "3": "proxy"}[
            mode
        ]
        if mode == "2":
            token = getpass.getpass("Token API Cloudflare (disembunyikan): ")
            if not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token):
                raise InstallError("Token Cloudflare tidak sah.")
            self.config["CF_API_TOKEN"] = token
        self.config["BIND_IP"] = "127.0.0.1" if mode == "3" else "0.0.0.0"
        port = choose_port(self.config["BIND_IP"], 8443 if mode == "3" else 443)
        self.config["HTTPS_PORT"] = str(port)
        self.config["PUBLIC_URL"] = f"https://{self.config['HOSTNAME']}" + (
            f":{port}" if port != 443 and mode != "3" else ""
        )
        self.write_runtime()
        self.state.pop("restored_isolated")
        self.save()
        self.start()
        configure_schedule(self)

    def export_snapshot(self, destination):
        destination = private_directory(destination)
        if destination.exists():
            raise InstallError(
                "Tujuan ekspor harus direktori baru pada media cadangan."
            )
        destination.mkdir(parents=True, mode=0o700)
        self.compose(
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0",
            "-v",
            f"{destination}:/export",
            "backup",
            "python",
            "-c",
            "from pathlib import Path; import os,re,shutil; from app.services.backup_crypto_service import verify_archive,encryption_key; p=Path('/app/backups/full'); files=sorted(x for x in p.iterdir() if re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{8}\\.absfull',x.name) and not x.is_symlink()); src=files[-1]; verify_archive(src,encryption_key()); dst=Path('/export')/src.name; shutil.copyfile(src,dst); verify_archive(dst,encryption_key()); os.chmod(dst,0o600); os.chown(dst,"
            + str(os.getuid())
            + ","
            + str(os.getgid())
            + ")",
            timeout=3900,
        )
        say(
            f"Cadangan lengkap terbaru disalin dan diverifikasi di {destination}. Simpan recovery.key secara terpisah."
        )

    def repair(self):
        self.ensure_no_orphans()
        if self.state.get("restored_isolated"):
            raise InstallError(
                "Hasil pemulihan belum diaktifkan. Jalankan aktifkan setelah layanan lama dihentikan."
            )
        required = ("compose.yml", "release.json", "manage.py", "release.py")
        if any(not (self.release / name).is_file() for name in required):
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                target = fetch(directory, self.state["version"])
                # Preserve damaged copies for diagnosis.
                if self.release.exists():
                    self.release.rename(
                        self.release.with_name(
                            self.release.name + ".rusak-" + secrets.token_hex(4)
                        )
                    )
                shutil.copytree(target, self.release)
        write_launcher(self.root)
        transaction = self.state.get("transaction")
        if transaction and transaction["phase"] == "backup":
            self.compose("start", *transaction.get("resume", [])) if transaction.get(
                "resume"
            ) else None
            self.state.pop("transaction")
            self.save()
            say("Cadangan yang terhenti tidak dipakai. Layanan sebelumnya dipulihkan.")
        elif transaction and transaction["phase"] == "migration":
            say(
                f"Migrasi sebelumnya terhenti. Cadangan sebelum migrasi: {transaction['backup']}"
            )
            if yes(
                "Coba lanjutkan versi tujuan? Jika tetap gagal, gunakan pulihkan ke instalasi baru"
            ):
                self.finish_update()
            return
        elif transaction:
            raise InstallError(
                "Tahap pemulihan belum selesai. Pertahankan arsip; ulangi pulihkan ke direktori kosong lain."
            )
        self.write_runtime()
        self.pull()
        self.start(admin=True)

    def logs(self, service):
        if service not in (*SERVICES, "db"):
            raise InstallError("Nama layanan tidak dikenal.")
        content = self.compose("logs", "--no-color", "--tail", "80", service).stdout
        for key in (
            "POSTGRES_PASSWORD",
            "WHATSAPP_BRIDGE_TOKEN",
            "BACKUP_ENCRYPTION_KEY",
            "CF_API_TOKEN",
        ):
            if self.config.get(key):
                content = content.replace(self.config[key], "[RAHASIA]")
        say(content)


def install_release(source, root):
    root = private_directory(root)
    if root.exists() and any(root.iterdir()):
        raise InstallError(
            "Direktori berisi berkas lain. Pilih direktori kosong; instalasi lama tidak ditimpa."
        )
    mode = ask(
        "HTTPS: 1) CA lokal, 2) Domain di Cloudflare, 3) Reverse proxy yang sudah ada",
        "1",
    )
    if mode not in {"1", "2", "3"}:
        raise InstallError("Pilih 1, 2, atau 3.")
    host = hostname(ask("Nama domain atau IPv4 LAN tetap server (contoh 192.168.1.10)"))
    if mode != "1" and re.fullmatch(r"[0-9.]+", host):
        raise InstallError("Mode domain/proxy memerlukan nama domain.")
    token = ""
    if mode == "2":
        say(
            "Token Cloudflare perlu Zone:DNS:Edit dan Zone:Zone:Read hanya untuk zona sekolah."
        )
        token = getpass.getpass("Token API Cloudflare (disembunyikan): ")
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token):
            raise InstallError("Format token Cloudflare tidak sah.")
    bind = "127.0.0.1" if mode == "3" else "0.0.0.0"
    port = choose_port(bind, 8443 if mode == "3" else 443)
    zone = ask("Zona waktu: 1) WIB, 2) WITA, 3) WIT", "1")
    if zone not in {"1", "2", "3"}:
        raise InstallError("Pilih zona waktu 1, 2, atau 3.")
    backup = private_directory(
        ask(
            "Direktori cadangan (boleh pada disk lain yang sudah dipasang)",
            str(root / "backups"),
        )
    )
    if (
        backup == root
        or root.is_relative_to(backup)
        or (
            backup.is_relative_to(root)
            and backup.relative_to(root).parts[0] != "backups"
        )
    ):
        raise InstallError(
            "Pilih subdirektori backups di instalasi atau direktori terpisah; jangan gunakan direktori instalasi/induknya sebagai tempat cadangan."
        )
    if backup.exists() and any(backup.iterdir()):
        raise InstallError(
            "Direktori cadangan harus baru/kosong agar berkas lain tidak tersentuh."
        )
    times = ask("Waktu cadangan database/foto (satu atau dua HH:MM)", "10:00,17:00")
    if not re.fullmatch(
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9](?:,(?:[01][0-9]|2[0-3]):[0-5][0-9])?", times
    ):
        raise InstallError("Isi satu atau dua waktu yang sah, contoh 10:00,17:00.")
    keep = ask("Jumlah hari cadangan database/foto yang disimpan", "14")
    if not keep.isdecimal() or not 1 <= int(keep) <= 365:
        raise InstallError("Retensi harus 1–365 hari.")
    say(
        f"\nLokasi: {root}\nHTTPS: {host}, port {port}\nCadangan: {backup}, pukul {times}\nInstaller membuat proyek Docker terpisah dan rahasia acak. Direktori cadangan baru akan dimiliki UID 10001."
    )
    say(
        "Cadangan pada disk yang sama tidak melindungi dari kerusakan disk. Simpan kunci pemulihan terpisah."
    )
    if not yes("Terapkan konfigurasi dan unduh image?"):
        say("Instalasi dibatalkan.")
        return
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    version = json.loads((source / "release.json").read_text())["version"]
    destination = root / "releases" / version
    destination.parent.mkdir(mode=0o700)
    shutil.copytree(source, destination)
    config = {
        "INSTALL_DIR": str(root),
        "HOSTNAME": host,
        "TLS_MODE": {"1": "internal", "2": "cloudflare", "3": "proxy"}[mode],
        "HTTPS_PORT": str(port),
        "BIND_IP": bind,
        "PUBLIC_URL": f"https://{host}"
        + (f":{port}" if port != 443 and mode != "3" else ""),
        "TIMEZONE": TIMEZONES[int(zone) - 1],
        "CF_API_TOKEN": token,
        "POSTGRES_PASSWORD": secrets.token_hex(32),
        "WHATSAPP_BRIDGE_TOKEN": secrets.token_hex(32),
        "BACKUP_ENCRYPTION_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "BACKUP_DIR": str(backup),
        "BACKUP_TIMES": times,
        "BACKUP_KEEP_DAILY": keep,
        "FULL_BACKUP_KEEP": "7",
    }
    env_write(root / "production.env", config)
    atomic(root / "recovery.key", config["BACKUP_ENCRYPTION_KEY"] + "\n")
    atomic(
        root / "state.json",
        json.dumps(
            {
                "format": 1,
                "version": version,
                "project": "absensa-" + secrets.token_hex(6),
                "initialized": False,
            }
        ),
    )
    write_launcher(root)
    installation = Installation(root)
    installation.write_runtime()
    installation.pull()
    # Own only the newly created, explicitly approved backup directory, not its parent.
    installation.prepare_backup_directory()
    say(
        f"Simpan {root / 'recovery.key'} di tempat aman terpisah dari arsip. Jangan kirim melalui pesan umum."
    )
    if yes("Nyalakan Absensa sekarang?", True):
        installation.start(admin=True)
        if yes("Buat dan verifikasi cadangan lengkap pertama?", True):
            installation.snapshot()
        configure_schedule(installation)
    else:
        say(
            f"Konfigurasi selesai; layanan belum dinyalakan. Jalankan: {root}/absensa mulai\nSaat pertama dijalankan, database dan administrator akan disiapkan."
        )


def write_launcher(root):
    # Launcher remains independent of version; state chooses the committed manager.
    atomic(
        root / "absensa",
        """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
root = Path(__file__).resolve().parent
state = json.loads((root / "state.json").read_text())
manager = root / "releases" / state["version"] / "manage.py"
os.execv(sys.executable, [sys.executable, str(manager), "--directory", str(root), *sys.argv[1:]])
""",
        0o700,
    )


def configure_schedule(installation):
    if not shutil.which("crontab"):
        say(
            "Penjadwal cron belum tersedia. Cadangan database/foto otomatis tetap aktif. Pasang cron melalui pengelola paket lalu jalankan ./absensa jadwal untuk cadangan lengkap."
        )
        return
    say(
        "Cadangan lengkap pukul 02:00 waktu server menghentikan Absensa sebentar, termasuk WhatsApp. Menyimpan 7 arsip lengkap terbaru. Cron memerlukan Linux yang tetap menyala."
    )
    if not yes("Tambahkan jadwal cadangan lengkap harian ke crontab pengguna ini?"):
        return
    value = ask("Jam cadangan lengkap (HH:MM, waktu server)", "02:00")
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise InstallError("Jam tidak sah.")
    keep = ask("Jumlah arsip lengkap terbaru yang disimpan", "7")
    if not keep.isdecimal() or not 1 <= int(keep) <= 365:
        raise InstallError("Retensi harus 1–365.")
    result = run(["crontab", "-l"], check=False)
    if result.returncode not in {0, 1} or (result.returncode == 1 and result.stdout):
        raise InstallError("Crontab tidak dapat diperiksa; jadwal lama tidak diubah.")
    marker = f"# absensa:{installation.state['project']}"
    lines = [line for line in result.stdout.splitlines() if not line.endswith(marker)]
    hour, minute = value.split(":")
    lines.append(
        f"{int(minute)} {int(hour)} * * * {installation.root}/absensa cadangkan >> {installation.root}/schedule.log 2>&1 {marker}"
    )
    run(["crontab", "-"], data="\n".join(lines) + "\n")
    installation.config["FULL_BACKUP_KEEP"] = keep
    env_write(installation.config_path, installation.config)
    say("Jadwal terpasang. Periksa ./absensa status dan schedule.log secara rutin.")


def restore(installation, archive, key_file, destination):
    # Recovery must remain available after a failed migration. It only reads the
    # source archive and creates a separate project; it never starts the source.
    archive, key_file = Path(archive).resolve(), Path(key_file).resolve()
    destination = private_directory(destination)
    if destination.exists():
        raise InstallError(
            "Tujuan pemulihan harus direktori baru yang belum ada. Data aktif tidak ditimpa."
        )
    key = key_file.read_text().strip()
    if len(base64.b64decode(key, validate=True)) != 32:
        raise InstallError("Kunci pemulihan tidak sah.")
    if not yes(
        f"Pulihkan ke proyek Docker baru di {destination}? Database aktif tidak diubah"
    ):
        return
    destination.mkdir(parents=True, mode=0o700)
    # Only the authenticated archive is extracted; no scripts from the snapshot run on host.
    with tempfile.TemporaryDirectory(prefix="restore-", dir=destination) as temporary:
        stage = Path(temporary)
        env_write(
            stage / "decrypt.env",
            {"BACKUP_ENCRYPTION_KEY": key, "DATABASE_URL": "postgresql://unused"},
        )
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0",
                "--env-file",
                str(stage / "decrypt.env"),
                "-v",
                f"{archive.parent}:/source:ro",
                "-v",
                f"{stage}:/recovery",
                installation.config["BACKUP_IMAGE"],
                "python",
                "-m",
                "app.jobs.deployment_archive",
                "unpack",
                f"/source/{archive.name}",
                "/recovery/unpacked",
            ],
            timeout=3900,
        )
        # Root container output becomes readable by the invoking owner, narrowly scoped.
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0",
                "-v",
                f"{stage}:/recovery",
                installation.config["BACKUP_IMAGE"],
                "python",
                "-c",
                f"import os; from pathlib import Path; p=Path('/recovery'); [(os.chown(x,{os.getuid()},{os.getgid()})) for x in [p,*p.rglob('*')]]",
            ]
        )
        unpacked = stage / "unpacked"
        config = env_read(unpacked / "config/production.env")
        old_state = json.loads((unpacked / "config/state.json").read_text())
        version = old_state["version"]
        version_tuple(version)
        # Re-fetch release with provenance verification instead of trusting archived code.
        with tempfile.TemporaryDirectory(dir=destination) as directory:
            release = fetch(directory, version)
            (destination / "releases").mkdir()
            shutil.copytree(release, destination / "releases" / version)
        config["INSTALL_DIR"] = str(destination)
        config["BACKUP_DIR"] = str(destination / "backups")
        config["BIND_IP"] = "127.0.0.1"
        config["TLS_MODE"] = "internal"
        config["CF_API_TOKEN"] = ""
        config["HTTPS_PORT"] = str(choose_port("127.0.0.1", 9443))
        config["PUBLIC_URL"] = f"https://{config['HOSTNAME']}:{config['HTTPS_PORT']}"
        (destination / "backups").mkdir(mode=0o700)
        env_write(destination / "production.env", config)
        atomic(destination / "recovery.key", key + "\n")
        atomic(
            destination / "state.json",
            json.dumps(
                {
                    "format": 1,
                    "version": version,
                    "project": "absensa-" + secrets.token_hex(6),
                    "initialized": False,
                    "transaction": {"phase": "restore"},
                }
            ),
        )
        write_launcher(destination)
        target = Installation(destination)
        target.write_runtime()
        target.pull()
        target.compose("up", "-d", "--wait", "db")
        target.compose(
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0",
            "-v",
            f"{unpacked}:/recovery:ro",
            "-v",
            f"{target.state['project']}_photos:/restore/photos",
            "-v",
            f"{target.state['project']}_whatsapp_auth:/restore/whatsapp",
            "-v",
            f"{target.state['project']}_caddy_data:/restore/caddy",
            "backup",
            "python",
            "-m",
            "app.jobs.deployment_archive",
            "files",
            "/recovery",
        )
        target.compose(
            "cp",
            str(unpacked / "database/database.dump"),
            "db:/tmp/absensa-restore.dump",
        )
        target.compose(
            "exec",
            "-T",
            "db",
            "pg_restore",
            "-U",
            "absensa",
            "-d",
            "absensa",
            "--no-owner",
            "--no-privileges",
            "--single-transaction",
            "--exit-on-error",
            "/tmp/absensa-restore.dump",
            timeout=3900,
        )
        target.compose("exec", "-T", "db", "rm", "/tmp/absensa-restore.dump")
        target.compose(
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0",
            "backup",
            "python",
            "-c",
            "import os; os.chown('/app/backups',10001,10001); os.chmod('/app/backups',0o700)",
        )
        target.prepare_socket()
        target.compose("up", "-d", "--wait", "--wait-timeout", "180", "web", "caddy")
        target.check_https()
        counts = target.compose(
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "absensa",
            "-d",
            "absensa",
            "-Atc",
            "SELECT 'siswa=' || count(*) FROM students; SELECT 'pemindaian=' || count(*) FROM scan_logs; SELECT 'migrasi=' || version_num FROM alembic_version;",
        ).stdout
        say("Hasil pemulihan terisolasi:\n" + counts)
        target.compose("stop", "web", "caddy", "db")
        target.state.pop("transaction")
        target.state["initialized"] = True
        target.state["restored_isolated"] = True
        target.save()
    say(
        f"Pemulihan terverifikasi dan dihentikan di {destination}. WhatsApp/penjadwal belum dinyalakan. Ikuti panduan pemulihan sebelum mengganti layanan sekolah."
    )


class IndonesianParser(argparse.ArgumentParser):
    def error(self, message):
        raise InstallError(
            "Argumen tidak dikenal atau tidak lengkap. Gunakan ./absensa --help untuk melihat perintah."
        )

    def format_help(self):
        return (
            super()
            .format_help()
            .replace("usage:", "Cara pakai:")
            .replace("positional arguments:", "Perintah:")
            .replace("options:", "Pilihan:")
        )


def main():
    os.umask(0o077)
    parser = IndonesianParser(
        description="Pasang dan kelola Absensa dengan aman", add_help=False
    )
    parser.add_argument("--help", action="help", help="Tampilkan bantuan")
    parser.add_argument(
        "--directory", default=str(Path.home() / "absensa"), help="Direktori instalasi"
    )
    parser.add_argument("--release", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "action",
        nargs="?",
        default="menu",
        choices=[
            "menu",
            "mulai",
            "henti",
            "ulang",
            "status",
            "log",
            "periksa",
            "perbarui",
            "perbaiki",
            "admin",
            "cadangkan",
            "jadwal",
            "pulihkan",
            "aktifkan",
            "ekspor",
        ],
    )
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    root = private_directory(args.directory)
    if args.action == "menu" and (root / "state.json").exists():
        say(
            "Instalasi Absensa ditemukan.\n1. Perbarui Absensa\n2. Perbaiki instalasi\n3. Batal"
        )
        choice = ask("Pilihan", "3")
        if choice == "3":
            return
        if choice not in {"1", "2"}:
            raise InstallError("Pilih 1, 2, atau 3.")
        args.action = {"1": "perbarui", "2": "perbaiki"}[choice]
    if args.action == "menu" and not (root / "state.json").exists():
        root = private_directory(ask("Direktori instalasi", str(root)))
        if (root / "state.json").exists():
            # Re-enter with the chosen directory, preserving the existing-install menu.
            sys.argv = [sys.argv[0], "--directory", str(root)]
            return main()
    host_check(root, resources=args.action not in {"henti", "status", "log", "periksa"})
    if not (root / "state.json").exists():
        if args.action != "menu" or args.release is None:
            raise InstallError(
                "Instalasi tidak ditemukan. Jalankan install.sh dari GitHub untuk memasang rilis stabil."
            )
        install_release(args.release, root)
        return
    # flock is released by the kernel on interruption; never delete a live lock.
    with (root / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstallError(
                "Operasi Absensa lain sedang berjalan. Tunggu sampai selesai."
            ) from exc
        installation = Installation(root)
        installation.diagnose("Mulai " + args.action)
        try:
            if args.action == "mulai":
                if installation.state.get("restored_isolated"):
                    raise InstallError(
                        "Instalasi ini hasil pemulihan terisolasi. Ikuti langkah pengaktifan pada panduan agar sesi WhatsApp tidak berjalan ganda."
                    )
                installation.start(admin=True)
            elif args.action == "henti":
                installation.compose("stop")
            elif args.action == "ulang":
                installation.guard()
                installation.compose("stop", *SERVICES)
                installation.start()
            elif args.action == "status":
                say(installation.compose("ps", "-a").stdout)
                say(
                    f"Versi: {installation.state['version']}\nAlamat: {installation.config['PUBLIC_URL']}\nOperasi terhenti: {'ya' if installation.state.get('transaction') else 'tidak'}"
                )
            elif args.action == "log":
                installation.logs(args.arguments[0] if args.arguments else "web")
            elif args.action == "periksa":
                installation.check_https()
            elif args.action == "admin":
                installation.guard()
                installation.migrate()
                installation.initialize_admin()
            elif args.action == "perbarui":
                installation.update()
            elif args.action == "perbaiki":
                installation.repair()
            elif args.action == "cadangkan":
                installation.snapshot()
            elif args.action == "aktifkan":
                installation.activate()
            elif args.action == "ekspor":
                if len(args.arguments) != 1:
                    raise InstallError(
                        "Gunakan: ./absensa ekspor /media/disk/cadangan-baru"
                    )
                installation.export_snapshot(args.arguments[0])
            elif args.action == "jadwal":
                configure_schedule(installation)
            elif args.action == "pulihkan":
                if len(args.arguments) != 3:
                    raise InstallError(
                        "Gunakan: ./absensa pulihkan /lokasi/arsip.absfull /lokasi/recovery.key /direktori/baru"
                    )
                restore(installation, *args.arguments)
        finally:
            installation.diagnose(
                "Akhir "
                + args.action
                + ("; perlu perbaikan" if installation.state.get("transaction") else "")
            )


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        say(
            "\nOperasi terhenti. Konfigurasi dan data tetap disimpan; jalankan perbaiki untuk melanjutkan."
        )
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - never expose raw errors or secrets
        say(
            "\n"
            + (
                str(exc)
                if isinstance(exc, InstallError)
                else "Konfigurasi/berkas tidak dapat dibaca. Periksa izin, ruang disk, dan kelengkapan instalasi; rahasia tidak ditampilkan."
            )
        )
        sys.exit(1)
