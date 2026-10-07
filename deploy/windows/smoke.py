"""Destructive ONLY to a new Absensa fixture on an ephemeral Windows CI runner.

Requires Administrator. Refuses an existing service or destination. Do not run on
school servers. Exercises actual SCM identities, packaged runtimes, TLS and PostgreSQL.
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def check(command, **kwargs):
    subprocess.run([str(p) for p in command], check=True, **kwargs)


def run_smoke():
    try:
        main()
    except Exception:
        # Also covers initial installation, before the service cleanup block exists.
        # Only operations.log is emitted: manage.py redacts its configured secrets.
        # Never print installation.json, recovery keys, or arbitrary service logs.
        program_data = os.environ.get("ProgramData")
        if program_data:
            log = Path(program_data) / "Absensa Integration Test/logs/operations.log"
            try:
                with log.open("rb") as stream:
                    stream.seek(0, os.SEEK_END)
                    start = max(0, stream.tell() - 65536)
                    stream.seek(start)
                    if start:
                        stream.readline()  # Discard any partial first line.
                    diagnostic = stream.read().decode("utf-8", errors="replace")
                print(f"Windows smoke failure; diagnostic tail: {log}", file=sys.stderr)
                for line in diagnostic.splitlines():
                    # Prefix prevents log content being interpreted as Actions commands.
                    print(f"operations.log | {line}", file=sys.stderr)
            except OSError as error:
                print(f"Cannot read Windows smoke diagnostic: {error}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    package = args.package.resolve()
    root = Path(os.environ["ProgramFiles"]) / "Absensa Integration Test"
    data = Path(os.environ["ProgramData"]) / "Absensa Integration Test"
    if root.exists() or data.exists():
        raise SystemExit("Fixture roots must be new")
    for name in ("PostgreSQL", "Web", "Scheduler", "Backup", "WhatsApp", "Caddy"):
        if (
            subprocess.run(
                ["sc.exe", "query", "Absensa" + name], capture_output=True, check=False
            ).returncode
            != 1060
        ):
            raise SystemExit("Refusing existing/unknown Absensa service")
    root.mkdir()
    (data / "config").mkdir(parents=True)
    (data / "logs").mkdir()
    shell = (
        Path(os.environ["SystemRoot"])
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    for folder in (root, data, data / "config", data / "logs"):
        check(
            [
                shell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                package / "host.ps1",
                "-Action",
                "private",
                "-Path",
                folder,
            ]
        )
    python = package / "python/python.exe"
    check(
        [
            python,
            package / "manage.py",
            "--root",
            root,
            "--data",
            data,
            "--hostname",
            "absensa.test",
            "--port",
            "18443",
            "--tls",
            "internal",
            "--timezone",
            "Asia/Jakarta",
            "--no-admin",
            "install",
        ]
    )
    spec = importlib.util.spec_from_file_location(
        "native_manage", package / "manage.py"
    )
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    # Shared durable publisher needs app on the test driver's path too.
    sys.path.insert(0, str(package / "web"))
    obj = manager.Installation(root, data)
    try:
        assert all(obj.running(role) for role in manager.SERVICES)
        original = obj.config.copy()
        # DLL loading, Cairo card primitives, archive import, timezone and image codecs.
        probe = """
import io,sys,zipfile
import runtime
runtime.prepare(sys.argv[1], 'maintenance')
from zoneinfo import ZoneInfo
from PIL import Image
import cairosvg
from app.services.import_archive_service import read_archive
from app.services.backup_crypto_service import verify_archive,encryption_key
assert str(ZoneInfo('Asia/Jakarta')) == 'Asia/Jakarta'
png=cairosvg.svg2png(bytestring=b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><rect width="20" height="10" fill="red"/></svg>')
assert Image.open(io.BytesIO(png)).size == (20,10)
from app.models.student import Student
from app.schemas.student_card import CardSettings
from app.services.student_card_service import render_student_card_png
card=render_student_card_png(Student(id=1,name='Siswa Windows',nisn='1234567890',current=True),CardSettings())
assert Image.open(io.BytesIO(card)).width > 100
b=io.BytesIO()
with zipfile.ZipFile(b,'w') as z: z.writestr('test.xlsx',b'archive DLL fixture')
assert read_archive(b.getvalue())[0][0][1] == b'archive DLL fixture'
"""
        check([obj.python, "-c", probe, data])
        # Execute Chrome in Session 0 as the real WhatsApp virtual account.
        # Only this test installation's script is instrumented, never the release ZIP.
        server = obj.release / "whatsapp/src/server.js"
        original_server = server.read_text()
        marker = data / "whatsapp/browser-probe.json"
        browser_probe = obj.release / "whatsapp/src/native-browser-probe.js"
        browser_probe.write_text(
            "const puppeteer=require('puppeteer'); const fs=require('node:fs'); "
            "(async()=>{const b=await puppeteer.launch({executablePath:process.env.CHROME_PATH,headless:true}); "
            "const p=await b.newPage(); await p.setContent('<title>Absensa service</title>'); "
            "const title=await p.title(); await b.close(); fs.writeFileSync("
            + json.dumps(str(marker))
            + ",JSON.stringify({title}));})().catch(e=>{console.error(e);process.exit(1)});\n"
        )
        obj.stop(("whatsapp",))
        try:
            server.write_text("require('./native-browser-probe');\n" + original_server)
            obj.start_services(("whatsapp",))
            import time

            for _ in range(60):
                if marker.exists():
                    break
                time.sleep(1)
            assert json.loads(marker.read_text())["title"] == "Absensa service"
        finally:
            obj.stop(("whatsapp",))
            server.write_text(original_server)
            browser_probe.unlink()
            obj.start_services(("whatsapp",))
        obj.pg(
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            database=obj.config["database"],
            input="CREATE TABLE native_smoke (value text); INSERT INTO native_smoke VALUES ('school fixture'); ALTER TABLE native_smoke OWNER TO absensa;\n",
        )
        photo = data / "photos" / obj.config["photo_tree"] / "fixture.png"
        photo.write_bytes(b"persistent photo fixture")
        # Idempotent bootstrap/repair never rotates secrets or initializes another database.
        check(
            [
                python,
                package / "manage.py",
                "--root",
                root,
                "--data",
                data,
                "--no-admin",
                "install",
            ]
        )
        obj = manager.Installation(root, data)
        assert (
            obj.config == original and photo.read_bytes() == b"persistent photo fixture"
        )
        full = obj.snapshot()
        assert full.is_file() and full.stat().st_size > 100
        obj.stop()
        obj.complete()  # Stop/start also checks workers and verifies TLS.
        # Candidate versions are fixtures, through the same update method after release
        # verification would have completed. No verification bypass exists in the CLI.
        with tempfile.TemporaryDirectory(prefix="absensa-upgrade-") as temp:
            target = Path(temp) / "candidate"
            shutil.copytree(package, target)
            manifest = json.loads((target / "release.json").read_text())
            current = list(manager.version(obj.state["version"]))
            current[2] += 1
            manifest["version"] = "v" + ".".join(map(str, current))
            (target / "release.json").write_text(json.dumps(manifest))
            obj.update(target)
            obj = manager.Installation(root, data)
            assert obj.state["version"] == manifest["version"] and not obj.state.get(
                "transaction"
            )
            assert obj.config == original and photo.is_file()
            # A broken migration must preserve its pre-update backup and block start.
            current[2] += 1
            manifest["version"] = "v" + ".".join(map(str, current))
            (target / "release.json").write_text(json.dumps(manifest))
            (target / "web/alembic/versions/native_broken.py").write_text(
                "raise RuntimeError('simulated migration failure')\n"
            )
            try:
                obj.update(target)
            except manager.OperationError:
                pass
            else:
                raise AssertionError("Broken migration unexpectedly succeeded")
            obj = manager.Installation(root, data)
            assert obj.state["transaction"]["phase"] == "migration"
            assert Path(obj.state["transaction"]["backup"]).is_file()
            assert not obj.running("web")
            (obj.release / "web/alembic/versions/native_broken.py").unlink()
            obj.repair()
            obj = manager.Installation(root, data)
        # Restore a current-version snapshot into NEW DB/photo trees, preserving old.
        full = obj.snapshot()
        before_db = obj.config["database"]
        with patch("builtins.input", return_value="PULIHKAN"):
            obj.restore(full, data / "config/recovery.key")
        assert obj.config["database"] != before_db
        assert obj.state["transaction"]["phase"] == "restored"
        assert not obj.running("scheduler")
        result = obj.pg(
            "psql",
            "-XAt",
            "-c",
            "SELECT value FROM native_smoke",
            database=obj.config["database"],
        )
        assert result.stdout.strip() == "school fixture"
        assert (
            data / "photos" / obj.config["photo_tree"] / "fixture.png"
        ).read_bytes() == photo.read_bytes()
        obj.complete()
        # Verify account identities and automatic startup in SCM, not just XML.
        script = "Get-CimInstance Win32_Service | Where-Object Name -like 'Absensa*' | Select-Object Name,StartName,StartMode | ConvertTo-Json"
        services = json.loads(
            subprocess.check_output(
                [str(shell), "-NoProfile", "-Command", script], text=True
            )
        )
        assert len(services) == 6
        for service in services:
            assert service["StartName"] == "NT SERVICE\\" + service["Name"]
            assert service["StartMode"] == "Auto"
        print(
            "Native Windows package/install/repair/start/TLS/migration/backup/restore/update/failure smoke passed."
        )
    finally:
        # CI-owned names only, after the initial no-existing-service guard.
        obj = manager.Installation(root, data)
        obj.set_start(False)
        obj.stop()
        for role in reversed(tuple(manager.SERVICES)):
            if obj.exists(role):
                obj.sc("delete", manager.SERVICES[role])
        obj.host("unfirewall")
        print("Test services removed; fixture data and logs retained:", data)


if __name__ == "__main__":
    run_smoke()
