"""Platform-independent safety tests; native service integration lives in smoke.py."""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "web"))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manage = load("windows_manage", "manage.py")
package = load("windows_package", "package.py")
smoke = load("windows_smoke", "smoke.py")


class WindowsTests(unittest.TestCase):
    def test_packaged_guide_links_to_its_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package.write_guide(root, "v1.1.0")
            guide = (root / "PANDUAN.md").read_text(encoding="utf-8")
            self.assertNotIn("](VALIDATION.md)", guide)
            self.assertIn(
                "](https://github.com/u70i1/absensa/blob/v1.1.0/deploy/windows/VALIDATION.md)",
                guide,
            )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.root = self.path / "Program Files/Absensa"
        self.data = self.path / "ProgramData/Absensa"
        self.root.mkdir(parents=True)
        (self.data / "config").mkdir(parents=True)
        self.obj = manage.Installation(self.root, self.data)
        self.obj.config = manage.new_config("absensa.school.test")
        self.obj.state = {
            "format": 1,
            "version": "v1.0.0",
            "root": str(self.root),
            "data": str(self.data),
            "initialized": True,
        }
        self.obj.save()

    def test_configuration_secrets_independent_and_secure_cookies(self):
        a = self.obj.config
        b = manage.new_config("absensa.school.test")
        for key in ("pg_password", "db_password", "bridge_token", "backup_key"):
            self.assertNotEqual(a[key], b[key])
        self.assertNotEqual(a["pg_password"], a["db_password"])
        env = self.obj.environment("web")
        self.assertEqual(env["ADMIN_COOKIE_SECURE"], "true")
        self.assertNotIn("BACKUP_ENCRYPTION_KEY", env)
        self.assertNotIn("DATABASE_URL", self.obj.environment("whatsapp"))
        self.assertNotIn("DATABASE_URL", self.obj.environment("caddy"))
        self.assertIn(str(self.data), env["PHOTOS_DIR"])
        self.assertNotIn(str(self.root), env["PHOTOS_DIR"])

    def test_failed_host_operation_reports_action_and_redacts_secrets(self):
        (self.data / "logs").mkdir()
        output = "SC failure " + " ".join(
            self.obj.config[key]
            for key in ("pg_password", "db_password", "bridge_token", "backup_key")
        )
        result = subprocess.CompletedProcess([], 1, stdout=output, stderr="error")
        with (
            patch.dict(manage.os.environ, {"SystemRoot": "C:/Windows"}),
            patch.object(manage.subprocess, "run", return_value=result),
            self.assertRaisesRegex(
                manage.OperationError, "host.ps1 service.*AbsensaWeb"
            ),
        ):
            self.obj.host("service", Name="AbsensaWeb")
        log = (self.data / "logs/operations.log").read_text()
        self.assertIn("host.ps1 service (AbsensaWeb): exit 1", log)
        self.assertIn("[RAHASIA]", log)
        for key in ("pg_password", "db_password", "bridge_token", "backup_key"):
            self.assertNotIn(self.obj.config[key], log)

    def test_smoke_initial_failure_prints_only_operations_log_and_preserves_error(self):
        fixture = self.path / "Absensa Integration Test"
        (fixture / "logs").mkdir(parents=True)
        (fixture / "logs/operations.log").write_text(
            "SC configuration failed\n::error::fixture\n"
        )
        (fixture / "installation.json").write_text("SECRET_CONFIG")
        output = io.StringIO()
        error = subprocess.CalledProcessError(1, ["manage.py", "install"])
        with (
            patch.dict(smoke.os.environ, {"ProgramData": str(self.path)}),
            patch.object(smoke, "main", side_effect=error),
            patch.object(smoke.sys, "stderr", output),
            self.assertRaises(subprocess.CalledProcessError) as caught,
        ):
            smoke.run_smoke()
        self.assertIs(caught.exception, error)
        self.assertIn("operations.log | SC configuration failed", output.getvalue())
        self.assertIn("operations.log | ::error::fixture", output.getvalue())
        self.assertNotIn("SECRET_CONFIG", output.getvalue())

    def test_smoke_missing_diagnostic_preserves_original_error(self):
        error = RuntimeError("original failure")
        with (
            patch.dict(smoke.os.environ, {"ProgramData": str(self.path)}),
            patch.object(smoke, "main", side_effect=error),
            patch.object(smoke.sys, "stderr", io.StringIO()),
            self.assertRaises(RuntimeError) as caught,
        ):
            smoke.run_smoke()
        self.assertIs(caught.exception, error)

    def test_host_validation_rejects_caddy_injection(self):
        for name in (
            "https://foo",
            "127.0.0.1",
            "0.0.0.0",
            "a.test {",
            "a.test\nx",
            "a.test:443",
            "-a.test",
        ):
            with self.subTest(name=name), self.assertRaises(manage.OperationError):
                manage.new_config(name)

    def test_services_quote_spaces_no_secrets_and_dependencies(self):
        for role in manage.APPLICATION:
            xml = manage.service_xml(role, self.root / "releases/v1.0.0", self.data)
            root = ET.fromstring(xml)
            self.assertEqual(root.findtext("id"), manage.SERVICES[role])
            self.assertIn('"', root.findtext("arguments"))
            self.assertEqual(root.findtext("startmode"), "Manual")
            self.assertEqual(root.find("onfailure").get("action"), "restart")
            self.assertIsNotNone(root.find("depend"))
            self.assertIsNone(root.find("interactive"))
            self.assertNotIn(self.obj.config["db_password"], xml)
            self.assertNotEqual(root.findtext("serviceaccount/username"), "LocalSystem")

    def registration_fixture(self, existing, owned=True):
        self.obj.release.mkdir(parents=True)
        (self.obj.release / "winsw.exe").write_bytes(b"pinned wrapper fixture")
        self.obj.exists = Mock(return_value=existing)
        self.obj.sc = Mock()
        self.obj.run = Mock()
        self.obj.host = Mock(return_value=SimpleNamespace(stdout="fixture firewall"))
        self.obj.set_start = Mock()
        binary = '"' + str(self.root) + '\\services\\Absensa.exe"'
        if not owned:
            binary = '"C:\\Another App\\service.exe"'
        return SimpleNamespace(
            HKEY_LOCAL_MACHINE=object(),
            OpenKey=Mock(side_effect=lambda *args: contextlib.nullcontext(object())),
            QueryValueEx=Mock(return_value=(binary, 1)),
        )

    def test_existing_services_reconfigured_in_place_for_repair_and_upgrade(self):
        registry = self.registration_fixture(existing=True)
        for installed_version in ("v1.0.0", "v1.1.0"):
            with self.subTest(version=installed_version):
                self.obj.state["version"] = installed_version
                self.obj.release.mkdir(parents=True, exist_ok=True)
                (self.obj.release / "winsw.exe").write_bytes(installed_version.encode())
                self.obj.sc.reset_mock()
                with patch.dict(sys.modules, {"winreg": registry}):
                    self.obj.register()
                # No wrapper refresh/install/uninstall, no service deletion and no
                # privileged account substitution during existing-service repair.
                self.obj.run.assert_not_called()
                for call in self.obj.sc.call_args_list:
                    self.assertNotEqual(call.args[0], "delete")
                    self.assertNotIn("obj=", call.args)
                for role in manage.APPLICATION:
                    name = manage.SERVICES[role]
                    executable = self.root / "services" / (name + ".exe")
                    self.assertEqual(
                        executable.read_bytes(), installed_version.encode()
                    )
                    definition = ET.parse(executable.with_suffix(".xml")).getroot()
                    self.assertEqual(
                        definition.findtext("executable"),
                        str(self.obj.release / "python/python.exe"),
                    )
                    dependency = (
                        manage.SERVICES["web"]
                        if role == "caddy"
                        else manage.SERVICES["postgres"]
                    )
                    self.obj.sc.assert_any_call(
                        "config",
                        name,
                        "binPath=",
                        '"' + str(executable) + '"',
                        "start=",
                        "demand",
                        "depend=",
                        dependency,
                        "DisplayName=",
                        definition.findtext("name"),
                    )
                    self.obj.sc.assert_any_call(
                        "description", name, definition.findtext("description")
                    )
                    self.obj.host.assert_any_call("service", Name=name)
                self.obj.set_start.assert_called_with(False)

    def test_fresh_services_use_supported_winsw_install(self):
        self.registration_fixture(existing=False)
        self.obj.register()
        for role in manage.APPLICATION:
            executable = self.root / "services" / (manage.SERVICES[role] + ".exe")
            self.obj.run.assert_any_call([executable, "install"])
        self.assertEqual(self.obj.run.call_count, len(manage.APPLICATION) + 1)

    def test_registration_refuses_existing_service_from_another_installation(self):
        registry = self.registration_fixture(existing=True, owned=False)
        with (
            patch.dict(sys.modules, {"winreg": registry}),
            self.assertRaisesRegex(manage.OperationError, "instalasi lain"),
        ):
            self.obj.register()
        self.obj.sc.assert_not_called()
        self.obj.run.assert_not_called()
        self.obj.host.assert_not_called()

    def test_caddy_uses_local_backend_and_never_embeds_token(self):
        self.obj.config.update(tls="cloudflare", cf_token="secret-fixture")
        result = manage.caddyfile(self.obj.config)
        self.assertIn("127.0.0.1:18088", result)
        self.assertIn("{env.CF_API_TOKEN}", result)
        self.assertNotIn("secret-fixture", result)
        self.assertIn("disable_redirects", result)

    def test_missing_data_never_creates_database(self):
        with self.assertRaisesRegex(manage.OperationError, "Penyimpanan"):
            self.obj.storage_check()
        self.assertFalse((self.data / "postgres").exists())

    def test_journal_blocks_start_and_update(self):
        self.obj.state["transaction"] = {"phase": "migration"}
        with self.assertRaisesRegex(manage.OperationError, "repair"):
            self.obj.guard()
        with self.assertRaises(manage.OperationError):
            self.obj.update()

    def test_failed_backup_resumes_services_without_migration(self):
        self.obj.guard = Mock()
        self.obj.running = lambda role: role == "web"
        self.obj.set_start = Mock()
        self.obj.stop = Mock()
        self.obj.start_services = Mock()
        self.obj.app = Mock(side_effect=manage.OperationError("failed backup"))
        with self.assertRaises(manage.OperationError):
            self.obj.snapshot(resume=False)
        self.assertNotIn("transaction", self.obj.state)
        self.obj.start_services.assert_any_call(["web"])
        self.assertEqual(self.obj.app.call_args.args[0], "app.jobs.backups")

    def test_update_backup_failure_never_selects_target(self):
        source = self.path / "target"
        source.mkdir()
        (source / "release.json").write_text(
            json.dumps(
                {"version": "v1.1.0", "upgrade_from_major": 1, "postgres_major": 18}
            )
        )
        self.obj.guard = Mock()
        self.obj.adopt_release = Mock()
        self.obj.snapshot = Mock(side_effect=manage.OperationError("backup failed"))
        self.obj.resume_target = Mock()
        with self.assertRaises(manage.OperationError):
            self.obj.update(source)
        self.assertEqual(self.obj.state["version"], "v1.0.0")
        self.obj.resume_target.assert_not_called()

    def test_failed_migration_keeps_target_and_backup_reference(self):
        source = self.path / "target"
        source.mkdir()
        (source / "release.json").write_text(
            json.dumps(
                {"version": "v1.1.0", "upgrade_from_major": 1, "postgres_major": 18}
            )
        )
        self.obj.guard = Mock()
        self.obj.adopt_release = Mock()
        self.obj.snapshot = Mock(return_value=self.data / "backups/recovery.absfull")
        self.obj.stop = Mock()
        self.obj.resume_target = Mock(
            side_effect=manage.OperationError("migration failed")
        )
        with self.assertRaises(manage.OperationError):
            self.obj.update(source)
        saved = json.loads(self.obj.state_path.read_text())
        self.assertEqual(saved["version"], "v1.1.0")
        self.assertEqual(saved["transaction"]["previous"], "v1.0.0")
        self.assertTrue(saved["transaction"]["backup"].endswith("recovery.absfull"))

    def test_restore_requires_explicit_activation_after_interruption(self):
        self.obj.state["transaction"] = {"phase": "restored"}
        self.obj.finish = Mock()
        with self.assertRaises(manage.OperationError):
            self.obj.repair()
        self.obj.finish.assert_not_called()

    def test_partial_cluster_not_reinitialized(self):
        self.obj.state["initialized"] = False
        (self.data / "postgres").mkdir()
        (self.data / "postgres/precious").write_text("school data")
        self.obj.run = Mock()
        with self.assertRaisesRegex(manage.OperationError, "belum lengkap"):
            self.obj.initialize_database()
        self.obj.run.assert_not_called()
        self.assertTrue((self.data / "postgres/precious").exists())

    def test_manifest_rejects_mismatched_platform(self):
        source = self.path / "source"
        source.mkdir()
        (source / "release.json").write_text(
            json.dumps(
                {
                    "version": "v1.1.0",
                    "format": 1,
                    "platform": "linux",
                    "architecture": "amd64",
                    "postgres_major": 18,
                }
            )
        )
        with self.assertRaises(manage.OperationError):
            self.obj.adopt_release(source)

    def test_initdb_restricted_user_grants_are_revoked_on_failure(self):
        self.obj.state["initialized"] = False
        self.obj.host = Mock()
        self.obj.run = Mock(side_effect=manage.OperationError("initdb failed"))
        with self.assertRaisesRegex(manage.OperationError, "initdb failed"):
            self.obj.initialize_database()
        granted = [
            c.kwargs
            for c in self.obj.host.call_args_list
            if c.args == ("grant-installer",)
        ]
        revoked = [
            c.kwargs
            for c in self.obj.host.call_args_list
            if c.args == ("revoke-installer",)
        ]
        self.assertEqual(len(granted), 5)
        self.assertEqual(revoked, list(reversed(granted)))
        self.assertFalse((self.data / "config/initdb.password").exists())

    def test_failed_service_start_keeps_journal_and_stops_partial_start(self):
        self.obj.state["transaction"] = {"phase": "migration", "backup": "safe.absfull"}
        self.obj.set_start = Mock()
        self.obj.start_services = Mock(
            side_effect=manage.OperationError("start failed")
        )
        self.obj.stop = Mock()
        self.obj.health = Mock()
        with self.assertRaises(manage.OperationError):
            self.obj.complete()
        self.obj.stop.assert_called_once_with(manage.APPLICATION)
        self.obj.set_start.assert_called_once_with(False)
        self.assertEqual(self.obj.state["transaction"]["phase"], "migration")

    def test_reinstall_repairs_missing_binaries_without_rotating_secrets(self):
        from argparse import Namespace

        source = self.path / "verified"
        source.mkdir()
        (source / "release.json").write_text(json.dumps({"version": "v1.0.0"}))
        (source / "absensa.ps1").write_text("# verified launcher")
        original = self.obj.config.copy()
        self.obj.state["uninstalled"] = True
        self.obj.set_start = Mock()
        self.obj.stop = Mock()
        self.obj.adopt_release = Mock()
        self.obj.repair = Mock()
        self.obj.admin = Mock()
        manage.install(self.obj, source, Namespace(no_admin=False))
        self.obj.adopt_release.assert_called_once_with(source)
        self.obj.repair.assert_called_once()
        self.obj.admin.assert_called_once()
        self.assertEqual(original, self.obj.config)
        self.assertNotIn("uninstalled", self.obj.state)
        self.assertTrue((self.root / "absensa.ps1").is_file())

    def test_nested_data_binary_roots_rejected_before_changes(self):
        with self.assertRaises(manage.OperationError):
            manage.Installation(self.root, self.root / "data")
        with self.assertRaises(manage.OperationError):
            manage.Installation(self.data / "binary", self.data)

    def test_https_cannot_collide_with_private_service_ports(self):
        for port in (55438, 18088, 13001):
            with self.assertRaises(manage.OperationError):
                manage.new_config("absensa.test", port)

    def test_dependency_locks_are_https_sha256_and_bootstrap_matches_gh(self):
        lock = json.loads((HERE / "dependencies.lock.json").read_text())
        for item in lock.values():
            self.assertTrue(item["url"].startswith("https://"))
            self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")
            self.assertNotIn("/latest", item["url"])
        bootstrap = (HERE.parents[1] / "install.ps1").read_text()
        self.assertIn(lock["gh"]["sha256"], bootstrap)
        self.assertIn(lock["gh"]["url"], bootstrap)
        self.assertIn("--deny-self-hosted-runners", bootstrap)
        self.assertIn("--source-ref", bootstrap)

    def test_checksum_dependency_failure_prevents_extraction(self):
        path = self.path / "fake.zip"
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum"):
            package.download(
                {"url": "https://example.test/fake.zip", "sha256": "0" * 64}, self.path
            )

    def test_release_rejects_missing_runtime_and_mutable_secrets(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            package.validate(self.root)
        for name in package.REQUIRED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        package.validate(self.root)
        (self.root / "web/.env").write_text("secret")
        with self.assertRaisesRegex(ValueError, "secret"):
            package.validate(self.root)

    def test_native_preflight_reports_versioned_cairo_without_loader_alias(self):
        native = self.path / "Native DLLs with spaces"
        native.mkdir()
        for name in ("cairo-2.dll", "archive.dll", "build.json"):
            (native / name).touch()
        with self.assertRaisesRegex(ValueError, "libcairo-2.dll.*cairo-2.dll"):
            package.validate_native(native)
        (native / "libcairo-2.dll").touch()
        package.validate_native(native)

    def test_native_preflight_requires_libarchive_and_build_metadata(self):
        native = self.path / "native"
        native.mkdir()
        (native / "libcairo-2.dll").touch()
        with self.assertRaisesRegex(ValueError, "archive.dll, build.json"):
            package.validate_native(native)


if __name__ == "__main__":
    unittest.main()
