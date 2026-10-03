"""Real isolated Docker exercise. Never cleans any pre-existing project/volume.

Run with a packaged release directory. --local uses explicitly named locally built
images; this test-only shim is not shipped inside the release/bootstrap.
"""

import argparse
import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import manage


def sql(site, statement):
    return site.compose(
        "exec", "-T", "db", "psql", "-U", "absensa", "-d", "absensa", "-Atc", statement
    ).stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("release", type=Path)
    parser.add_argument("--local", action="store_true")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove only this run's test containers and networks; retain data volumes and files",
    )
    args = parser.parse_args()
    source = args.release.resolve()
    temporary = Path(tempfile.mkdtemp(prefix="absensa-smoke-"))
    root = temporary / "installed"
    sites = []
    original_runtime = manage.Installation.write_runtime
    local_images = {
        "web": "absensa-web:installer-test",
        "backup": "absensa-backup:installer-test",
        "whatsapp": "absensa-whatsapp:installer-e2e",
        "caddy": "absensa-caddy:installer-test",
        "postgres": "postgres:18.4-alpine",
    }

    def runtime(site):
        original_runtime(site)
        if args.local:
            site.config.update(
                {name.upper() + "_IMAGE": image for name, image in local_images.items()}
            )
            manage.env_write(site.config_path, site.config)

    original_version = json.loads((source / "release.json").read_text())["version"]
    parts = list(manage.version_tuple(original_version))
    parts[2] += 1
    update_version = "v" + ".".join(map(str, parts))

    def fake_fetch(directory, tag=None):
        target = Path(directory) / "release"
        shutil.copytree(source, target)
        tag = tag or update_version
        if tag:
            manifest = json.loads((target / "release.json").read_text())
            manifest["version"] = tag
            (target / "release.json").write_text(json.dumps(manifest))
        return target

    # No school secrets: explicit synthetic credentials, input and data.
    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(manage.Installation, "write_runtime", runtime))
    if args.local:
        stack.enter_context(
            patch.object(manage.Installation, "pull", lambda self: None)
        )
    stack.enter_context(patch.object(manage, "fetch", fake_fetch))
    try:
        answers = ["1", "absensa.test", "1", str(root / "backups"), "10:00,17:00", "14"]
        with (
            patch.object(manage, "ask", side_effect=answers),
            patch.object(manage, "choose_port", return_value=19443),
            patch.object(manage, "yes", side_effect=[True, False]),
        ):
            manage.install_release(source, root)
        site = manage.Installation(root)
        sites.append(site)
        assert not site.running(), "Choosing no startup must leave all services stopped"
        runtime(site)
        # Model an interrupted initial setup: pull failed before backup ownership
        # was transferred to the container UID. Repair must complete that step.
        site.compose(
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0",
            "backup",
            "python",
            "-c",
            f"import os; os.chown('/app/backups',{os.getuid()},{os.getgid()}); os.chmod('/app/backups',0o700)",
        )
        with (
            patch.object(manage, "yes", return_value=True),
            patch.object(manage, "ask", return_value="smoke-admin"),
            patch.object(
                manage.getpass, "getpass", return_value="synthetic-smoke-password-123"
            ),
        ):
            site.repair()
        first_hash = sql(
            site, "SELECT password_hash FROM admins WHERE username='smoke-admin'"
        )
        with patch.object(
            manage.getpass,
            "getpass",
            side_effect=AssertionError("Admin must not be prompted again"),
        ):
            site.initialize_admin()
        assert first_hash == sql(
            site, "SELECT password_hash FROM admins WHERE username='smoke-admin'"
        )
        sql(
            site,
            "INSERT INTO students(name,nisn,current,photo_path) VALUES('Siswa Pengujian','1234567890',true,'smoke.jpg'); INSERT INTO scan_logs(student_id,name) SELECT id,name FROM students;",
        )
        site.compose(
            "exec",
            "-T",
            "web",
            "python",
            "-c",
            "from pathlib import Path; Path('/app/photos/smoke.jpg').write_bytes(b'photo-smoke-fixture')",
        )
        config = json.loads(site.compose("config", "--format", "json").stdout)
        assert all(
            "ports" not in service
            for name, service in config["services"].items()
            if name != "caddy"
        )
        # Login exercises proxy headers, same-origin CSRF and Secure cookies over verified HTTPS.
        response = manage.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--fail",
                "--noproxy",
                "*",
                "--cacert",
                str(root / "root-ca.crt"),
                "--resolve",
                "absensa.test:19443:127.0.0.1",
                "-D",
                "-",
                "-H",
                "Origin: https://absensa.test:19443",
                "--data",
                "username=smoke-admin&password=synthetic-smoke-password-123",
                "https://absensa.test:19443/admin",
            ]
        ).stdout
        assert "secure" in response.lower(), response[:200]
        site.compose("up", "-d", "--force-recreate", "--wait", "web")
        assert sql(site, "SELECT count(*) FROM students") == "1"
        snapshot = site.snapshot()
        exported = temporary / "external-copy"
        site.export_snapshot(exported)
        assert len(list(exported.glob("*.absfull"))) == 1
        assert site.state.get("transaction") is None
        assert "web" in site.running()
        restored = temporary / "restored"
        with (
            patch.object(manage, "yes", return_value=True),
            patch.object(manage, "choose_port", return_value=19444),
        ):
            manage.restore(site, snapshot, root / "recovery.key", restored)
        target = manage.Installation(restored)
        sites.append(target)
        runtime(target)
        target.compose("up", "-d", "--wait", "db")
        assert sql(target, "SELECT count(*) FROM students") == "1"
        assert sql(target, "SELECT count(*) FROM scan_logs") == "1"
        assert (
            sql(target, "SELECT password_hash FROM admins WHERE username='smoke-admin'")
            == first_hash
        )
        restored_photo = target.compose(
            "run",
            "--rm",
            "--no-deps",
            "web",
            "python",
            "-c",
            "from pathlib import Path; assert Path('/app/photos/smoke.jpg').read_bytes()==b'photo-smoke-fixture'",
        )
        assert restored_photo.returncode == 0
        assert "whatsapp" not in target.running()
        assert "scheduler" not in target.running()
        with patch.object(manage, "yes", return_value=True):
            site.update()
        assert site.state["version"] == update_version
        assert sql(site, "SELECT count(*) FROM students") == "1"
        assert first_hash == sql(
            site, "SELECT password_hash FROM admins WHERE username='smoke-admin'"
        )
        # A real migration error leaves the application stopped and a durable journal.
        version = site.state["version"]
        next_version = "v" + str(int(version[1:].split(".")[0])) + ".999.999"
        candidate = site.root / "releases" / next_version
        shutil.copytree(site.release, candidate)
        manifest = json.loads((candidate / "release.json").read_text())
        manifest["version"] = next_version
        (candidate / "release.json").write_text(json.dumps(manifest))
        text = (
            (candidate / "compose.yml")
            .read_text()
            .replace(
                "command: [alembic, upgrade, head]",
                "command: [alembic, upgrade, revision_that_does_not_exist]",
            )
        )
        (candidate / "compose.yml").write_text(text)
        site.compose("stop", *manage.SERVICES)
        site.state["transaction"] = {
            "phase": "migration",
            "target": next_version,
            "previous": version,
            "backup": str(snapshot),
        }
        site.save()
        try:
            site.finish_update()
        except manage.InstallError:
            pass
        else:
            raise AssertionError("Failed migration must stop update")
        assert site.state["transaction"]["target"] == next_version
        assert "web" not in site.running()
        # A failed migration must not lock the operator out of isolated recovery.
        with (
            patch.object(manage, "yes", return_value=True),
            patch.object(manage, "choose_port", return_value=19445),
        ):
            manage.restore(
                site, snapshot, root / "recovery.key", temporary / "recovered-failure"
            )
        assert site.state["transaction"]["target"] == next_version
        assert "web" not in site.running()
        # Repair retries the target migration, never silently switches images backward.
        (candidate / "compose.yml").write_text((source / "compose.yml").read_text())
        with patch.object(manage, "yes", return_value=True):
            site.repair()
        assert not site.state.get("transaction")
        assert sql(site, "SELECT count(*) FROM students") == "1"
        assert first_hash == sql(
            site, "SELECT password_hash FROM admins WHERE username='smoke-admin'"
        )
        print(
            "PASSED: deferred startup, migrations, idempotent admin creation, TLS/CSRF/Secure cookies, persistence, full backups, isolated restoration, failed migrations, and repair."
        )
    finally:
        # Cleanup is opt-in and scoped to newly created projects; never remove volumes.
        for path in (root, temporary / "restored", temporary / "recovered-failure"):
            if (path / "state.json").exists():
                try:
                    site = manage.Installation(path)
                    runtime(site)
                    if args.cleanup:
                        site.compose("down", check=False)
                    else:
                        site.compose("stop", check=False)
                except Exception:
                    pass
        stack.close()
        print("Test artifacts retained:", temporary)


if __name__ == "__main__":
    main()
