"""Platform-independent safety tests; native service integration lives in smoke.py."""

import contextlib
import importlib.util
import io
import json
import ssl
import os
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
runtime = load("windows_runtime", "runtime.py")


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

    def test_service_interrupt_is_clean_but_crashes_propagate(self):
        for role in ("scheduler", "backup", "caddy", "whatsapp"):
            with (
                patch.object(
                    sys, "argv", ["runtime", "--data", str(self.data), "--role", role]
                ),
                patch.object(runtime, "run", side_effect=KeyboardInterrupt),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                runtime.main()
            self.assertIn("Service stop requested", output.getvalue())
        with (
            patch.object(
                sys, "argv", ["runtime", "--data", str(self.data), "--role", "backup"]
            ),
            patch.object(runtime, "run", side_effect=RuntimeError("actual crash")),
            self.assertRaisesRegex(RuntimeError, "actual crash"),
        ):
            runtime.main()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "runtime",
                    "--data",
                    str(self.data),
                    "--role",
                    "maintenance",
                    "alembic",
                ],
            ),
            patch.object(runtime, "run", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            runtime.main()

    def test_child_interrupt_waits_for_graceful_shutdown(self):
        for code, expected in ((0, 0), (0xC000013A, 0), (7, 7)):
            child = Mock()
            child.wait.side_effect = [KeyboardInterrupt, code]
            with patch.object(runtime.subprocess, "Popen") as popen:
                popen.return_value.__enter__.return_value = child
                self.assertEqual(runtime.run_child(["fixture"], self.data), expected)
            child.wait.assert_called_with(timeout=100)
            child.terminate.assert_not_called()
            child.kill.assert_not_called()

    def test_child_shutdown_timeout_is_bounded_and_reported(self):
        child = Mock()
        child.wait.side_effect = [
            KeyboardInterrupt,
            subprocess.TimeoutExpired("fixture", 100),
            0,
        ]
        with (
            patch.object(runtime.subprocess, "Popen") as popen,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            popen.return_value.__enter__.return_value = child
            self.assertEqual(runtime.run_child(["fixture"], self.data), 0)
        child.terminate.assert_called_once()
        self.assertIn("timed out", output.getvalue())

    def test_bom_configuration_is_read_without_changing_secrets(self):
        for path, value in (
            (self.obj.state_path, self.obj.state),
            (self.obj.config_path, self.obj.config),
        ):
            path.write_text(json.dumps(value), encoding="utf-8-sig")
        loaded = manage.Installation(self.root, self.data)
        self.assertEqual(loaded.state, self.obj.state)
        self.assertEqual(loaded.config, self.obj.config)
        loaded.save()
        self.assertFalse(self.obj.state_path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_malformed_json_encoding_and_missing_fields_are_actionable(self):
        for raw, message in (
            (b'{"password":"PRIVATE",', "baris 1"),
            (b"\xff\xfeBAD", "encoding harus UTF-8"),
            (b"{}", "objek JSON"),
            (b"[]", "objek JSON"),
            (b'{"format":1}', "field wajib tidak ada"),
        ):
            with self.subTest(raw=raw):
                self.obj.config_path.write_bytes(raw)
                with self.assertRaisesRegex(manage.OperationError, message) as error:
                    manage.Installation(self.root, self.data)
                self.assertIn(str(self.obj.config_path), str(error.exception))
                self.assertNotIn("PRIVATE", str(error.exception))
                self.assertEqual(self.obj.config_path.read_bytes(), raw)

    def test_configuration_rejects_invalid_types_ports_keys_and_journals(self):
        manage.write_json(self.obj.config_path, self.obj.config)
        for field, value in (
            ("https_port", True),
            ("https_port", 18088),
            ("host", []),
            ("backup_key", "PRIVATE"),
            ("database", "../other"),
            ("db_password", "PRIVATE"),
        ):
            config = dict(self.obj.config, **{field: value})
            manage.write_json(self.obj.config_path, config)
            with self.assertRaises(manage.OperationError) as error:
                manage.Installation(self.root, self.data)
            self.assertNotIn("PRIVATE", str(error.exception))
        manage.write_json(self.obj.config_path, self.obj.config)
        for transaction in (
            None,
            {},
            {"phase": "unknown"},
            {"phase": "backup", "resume": ["other"]},
        ):
            manage.write_json(
                self.obj.state_path, dict(self.obj.state, transaction=transaction)
            )
            with self.assertRaisesRegex(manage.OperationError, "transaction"):
                manage.Installation(self.root, self.data)

    def test_interrupted_atomic_write_preserves_authoritative_state(self):
        before = self.obj.state_path.read_bytes()
        with (
            patch(
                "app.services.durable_file.publish", side_effect=OSError("interrupted")
            ),
            self.assertRaisesRegex(OSError, "interrupted"),
        ):
            manage.write_json(self.obj.state_path, {"version": "v99.0.0"})
        self.assertEqual(self.obj.state_path.read_bytes(), before)
        manage.write_json(self.obj.config_path, self.obj.config)
        loaded = manage.Installation(self.root, self.data)
        self.assertEqual(loaded.state, self.obj.state)
        self.assertTrue(list(self.data.glob("state.json.new-*")))

    def test_missing_config_never_generates_replacement_secrets(self):
        with (
            patch.object(manage, "new_config") as new,
            self.assertRaisesRegex(manage.OperationError, "konfigurasi hilang"),
        ):
            manage.Installation(self.root, self.data)
        new.assert_not_called()
        self.assertFalse(self.obj.config_path.exists())

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

    def test_expected_scm_codes_do_not_create_error_logs(self):
        missing = subprocess.CompletedProcess([], 1060, stdout="missing", stderr="")
        stopped = subprocess.CompletedProcess([], 1062, stdout="stopped", stderr="")
        query = subprocess.CompletedProcess(
            [], 0, stdout="STATE : 1 STOPPED", stderr=""
        )
        with (
            patch.dict(manage.os.environ, {"SystemRoot": "C:/Windows"}),
            patch.object(
                manage.subprocess, "run", side_effect=[missing, missing, stopped, query]
            ),
        ):
            self.assertFalse(self.obj.exists("web"))
            self.assertFalse(self.obj.running("web"))
            with patch.object(self.obj, "exists", return_value=True):
                self.obj.stop(("web",))
        self.assertFalse((self.data / "logs/operations.log").exists())

    def test_unexpected_scm_codes_are_logged_and_fail(self):
        (self.data / "logs").mkdir()
        for method in (self.obj.exists, self.obj.running):
            result = subprocess.CompletedProcess(
                [], 5, stdout="Access denied", stderr=""
            )
            with (
                patch.dict(manage.os.environ, {"SystemRoot": "C:/Windows"}),
                patch.object(manage.subprocess, "run", return_value=result),
                self.assertRaises(manage.OperationError),
            ):
                method("web")
        log = (self.data / "logs/operations.log").read_text()
        self.assertIn("exit 5", log)
        self.assertIn("Access denied", log)
        # An expected status is scoped to its operation, not ignored globally.
        result = subprocess.CompletedProcess([], 1062, stdout="unexpected", stderr="")
        with (
            patch.object(manage.subprocess, "run", return_value=result),
            self.assertRaises(manage.OperationError),
        ):
            self.obj.run(["sc.exe", "start", "AbsensaWeb"])

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

    def test_native_smoke_selects_active_ipv4_without_assuming_physical_adapter(self):
        network = {
            "addresses": [
                dict(address="127.0.0.1", interface="loopback"),
                dict(address="169.254.1.2", interface="unconfigured"),
                dict(address="192.168.0.10", interface="vEthernet"),
            ]
        }
        self.assertEqual(smoke.fixture_address(network), "192.168.0.10")
        with self.assertRaisesRegex(RuntimeError, "No active LAN IPv4"):
            smoke.fixture_address({"addresses": network["addresses"][:2]})

    def test_smoke_interruption_hook_is_fixture_only_and_restored(self):
        fixture = SimpleNamespace(
            new_config=manage.new_config,
            Installation=type("Installer", (), {"health": lambda self: None}),
            OperationError=manage.OperationError,
        )
        original = fixture.Installation.health

        def main():
            with self.assertRaisesRegex(
                manage.OperationError, "simulated interruption"
            ):
                fixture.Installation().health()

        fixture.main = main
        with (
            patch.dict(sys.modules, {"manage": fixture}),
            patch.dict(smoke.os.environ, {"ABSENSA_SMOKE_INTERRUPT_INSTALL": "1"}),
            patch.object(sys, "argv", ["fixture", "{}", "install"]),
        ):
            exec(smoke.INSTALL_FIXTURE, {})
        self.assertIs(fixture.Installation.health, original)

    def test_smoke_ports_skip_busy_and_reserved_ports_and_release_probes(self):
        probes = []

        def socket_fixture():
            probe = Mock()
            probes.append(probe)
            if len(probes) in (1, 3):
                probe.bind.side_effect = OSError("busy or excluded port")
            return probe

        with patch.object(smoke.socket, "socket", side_effect=socket_fixture):
            ports = smoke.fixture_ports()
        self.assertEqual(
            ports,
            {
                "https_port": 20001,
                "pg_port": 20003,
                "web_port": 20004,
                "bridge_port": 20005,
            },
        )
        for probe in probes:
            probe.close.assert_called_once_with()
        probes[1].bind.assert_called_once_with(("0.0.0.0", 20001))
        probes[3].bind.assert_called_once_with(("127.0.0.1", 20003))

    def test_smoke_port_exhaustion_fails_without_reusing_an_unavailable_port(self):
        probe = Mock()
        probe.bind.side_effect = OSError("reserved")
        with (
            patch.object(smoke.socket, "socket", return_value=probe),
            self.assertRaisesRegex(RuntimeError, "No free ports"),
        ):
            smoke.fixture_ports()
        self.assertEqual(probe.close.call_count, 1000)

    def test_smoke_install_overrides_only_fixture_config_and_preserves_cli(self):
        ports = {
            "https_port": 20001,
            "pg_port": 20003,
            "web_port": 20004,
            "bridge_port": 20005,
        }
        observed = {}
        fixture = SimpleNamespace(new_config=manage.new_config)

        def main():
            observed["config"] = fixture.new_config("absensa.test", ports["https_port"])
            observed["argv"] = sys.argv.copy()

        fixture.main = main
        arguments = [
            "--root",
            "C:/Program Files/Absensa Integration Test",
            "--no-admin",
            "install",
        ]
        with (
            patch.dict(sys.modules, {"manage": fixture}),
            patch.object(sys, "argv", ["-c", json.dumps(ports), *arguments]),
        ):
            # Execute only our checked-in child entry point, never downloaded input.
            exec(compile(smoke.INSTALL_FIXTURE, "<install fixture>", "exec"), {})  # noqa: S102
        self.assertEqual(observed["argv"], ["manage.py", *arguments])
        for key, port in ports.items():
            self.assertEqual(observed["config"][key], port)
        self.assertIs(fixture.new_config, manage.new_config)
        self.assertEqual(manage.new_config("absensa.test")["pg_port"], 55438)

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

    def health_fixture(self):
        self.obj.pg = Mock(return_value=SimpleNamespace(stdout="1\n"))
        self.obj.running = Mock(return_value=True)
        for role in ("scheduler", "backup"):
            directory = self.data / "health" / role
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"absensa-{role}.heartbeat").touch()
        bridge = Mock()
        bridge.getresponse.return_value.status = 200
        bridge.getresponse.return_value.read.return_value = b'{"ok":true}'
        self.addCleanup(patch.stopall)
        patch.object(manage.ssl, "create_default_context").start()
        patch.object(manage.http.client, "HTTPConnection", return_value=bridge).start()
        probe = patch.object(
            manage, "https_health", return_value=(200, {"ok": True})
        ).start()
        return probe, bridge

    def test_health_diagnostics_collect_independent_failures_and_redact(self):
        probe, bridge = self.health_fixture()
        probe.side_effect = ssl.SSLError(
            "alert internal error " + self.obj.config["db_password"]
        )
        self.obj.pg.side_effect = OSError("connection refused")
        self.obj.running.side_effect = lambda role: role != "scheduler"
        (self.data / "health/scheduler/absensa-scheduler.heartbeat").unlink()
        os.utime(self.data / "health/backup/absensa-backup.heartbeat", (1, 1))
        bridge.request.side_effect = ConnectionRefusedError("bridge refused")
        failures = "\n".join(self.obj.health_failures())
        for expected in (
            "TLS handshake failed",
            "Database 127.0.0.1",
            "connection refused",
            "AbsensaScheduler service stopped",
            "scheduler heartbeat missing",
            "backup heartbeat stale",
            "WhatsApp 127.0.0.1",
            "bridge refused",
        ):
            self.assertIn(expected, failures)
        self.assertNotIn(self.obj.config["db_password"], failures)
        bridge.close.assert_called_once()

    def test_health_distinguishes_certificate_status_and_payload_errors(self):
        probe, bridge = self.health_fixture()
        probe.side_effect = ssl.SSLCertVerificationError("IP mismatch")
        self.assertIn(
            "certificate verification failed", "\n".join(self.obj.health_failures())
        )
        probe.side_effect = None
        for status, body, expected in (
            (503, {"ok": False}, "unexpected status 503"),
            (200, [], "unhealthy body"),
        ):
            probe.return_value = (status, body)
            self.assertIn(expected, "\n".join(self.obj.health_failures()))
        probe.return_value = (200, {"ok": True})
        bridge.getresponse.return_value.status = 502
        self.assertIn(
            "WhatsApp /health returned unexpected status 502",
            "\n".join(self.obj.health_failures()),
        )

    def test_health_retries_and_preserves_final_diagnostics(self):
        self.obj.network_preflight = Mock()
        self.obj.health_failures = Mock(
            return_value=["HTTPS TLS handshake failed: fixture"]
        )
        with (
            patch.object(manage.time, "sleep") as sleep,
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(manage.OperationError, "handshake"),
        ):
            self.obj.health(attempts=2)
        sleep.assert_called_once_with(2)
        log = (self.data / "logs/operations.log").read_text()
        self.assertIn("RETRY 1/2", log)
        self.assertIn("FINAL FAILURE 2/2", log)
        self.obj.state["transaction"] = {"phase": "install"}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.obj.status()
        self.assertIn("install", output.getvalue())
        self.assertIn("FINAL FAILURE", output.getvalue())

    def test_health_recovers_from_transient_failure(self):
        self.obj.config["tls"] = "cloudflare"
        self.obj.health_failures = Mock(side_effect=[["temporary"], []])
        with (
            patch.object(manage.time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.obj.health(attempts=2)
        log = (self.data / "logs/operations.log").read_text()
        self.assertIn("Health OK", log)
        self.assertNotIn("FINAL FAILURE", log)

    def test_network_preflight_reports_virtual_interface_dhcp_dns_and_profiles(self):
        network = dict(
            addresses=[
                dict(
                    address="192.168.0.10", interface="vEthernet (LAN)", dhcp="Enabled"
                )
            ],
            profiles=[dict(interface="vEthernet (LAN)", category="Public")],
            firewall=[dict(name="Public", enabled=True)],
        )
        self.obj.host = Mock(return_value=SimpleNamespace(stdout=json.dumps(network)))
        self.obj.config["host"] = "192.168.0.10"
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.obj.network_preflight()
        self.assertIn("vEthernet", output.getvalue())
        self.assertIn("reservasi DHCP", output.getvalue())
        self.assertIn("Public", output.getvalue())
        self.assertNotIn("WARNING", output.getvalue())
        self.obj.host.assert_called_once_with("network")
        self.obj.config["host"] = "192.168.1.10"
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.obj.network_preflight()
        self.assertIn("tidak cocok", output.getvalue())
        self.obj.config["host"] = "school.test"
        with (
            patch.object(
                manage.socket, "getaddrinfo", side_effect=OSError("DNS unavailable")
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.obj.network_preflight()
        self.assertIn("DNS unavailable", output.getvalue())
        with (
            patch.object(
                manage.socket,
                "getaddrinfo",
                return_value=[(None, None, None, None, ("192.168.0.10", 443))],
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.obj.network_preflight()
        self.assertIn("Network DNS school.test: 192.168.0.10", output.getvalue())
        self.assertNotIn("tidak cocok", output.getvalue())

    def test_status_without_state_is_read_only(self):
        self.obj.state = self.obj.config = None
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.obj.status()
        self.assertIn("belum terpasang", output.getvalue())

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
        self.assertEqual(
            [c.args for c in self.obj.set_start.call_args_list], [(False,), (False,)]
        )
        self.assertEqual(self.obj.state["transaction"]["phase"], "migration")

    def test_finalization_scm_failure_keeps_durable_journal_then_repair_succeeds(self):
        self.obj.state.update(initialized=False, transaction={"phase": "install"})
        self.obj.start_services = Mock()
        self.obj.health = Mock()
        self.obj.stop = Mock()
        self.obj.set_start = Mock(
            side_effect=[None, manage.OperationError("SCM failed"), None]
        )
        with self.assertRaisesRegex(manage.OperationError, "SCM failed"):
            self.obj.complete()
        saved = json.loads(self.obj.state_path.read_text())
        self.assertFalse(saved["initialized"])
        self.assertFalse(saved["autostart"])
        self.assertEqual(saved["transaction"], {"phase": "install"})
        self.obj.stop.assert_called_once_with(manage.APPLICATION)
        self.obj.set_start = Mock()
        self.obj.complete()
        saved = json.loads(self.obj.state_path.read_text())
        self.assertTrue(saved["initialized"] and saved["autostart"])
        self.assertNotIn("transaction", saved)

    def test_finish_orders_migration_health_startup_and_preserves_data(self):
        self.obj.state.update(initialized=False, transaction={"phase": "install"})
        precious = self.data / "school-data"
        precious.write_bytes(b"existing school data")
        config = self.obj.config.copy()
        events = []
        for name in (
            "stop",
            "configure",
            "initialize_database",
            "register",
            "create_database",
            "migrate",
            "start_services",
            "health",
        ):
            setattr(
                self.obj,
                name,
                Mock(side_effect=lambda *a, name=name: events.append(name)),
            )

        def startup(automatic):
            events.append("auto" if automatic else "manual")
            self.assertIn("transaction", json.loads(self.obj.state_path.read_text()))

        self.obj.set_start = startup
        with patch.object(manage, "RELEASE", self.obj.release):
            self.obj.repair()
            self.obj.storage_check = Mock()
            self.obj.repair()
        self.assertEqual(events.count("migrate"), 2)
        self.assertLess(events.index("migrate"), events.index("health"))
        self.assertLess(events.index("health"), events.index("auto"))
        self.assertEqual(precious.read_bytes(), b"existing school data")
        self.assertEqual(config, self.obj.config)
        self.assertNotIn("transaction", json.loads(self.obj.state_path.read_text()))

    def test_failed_health_and_failed_cleanup_preserve_original_error(self):
        self.obj.state.update(initialized=False, transaction={"phase": "install"})
        self.obj.set_start = Mock()
        self.obj.start_services = Mock()
        self.obj.health = Mock(side_effect=manage.OperationError("TLS failed"))
        self.obj.stop = Mock(side_effect=manage.OperationError("stop failed"))
        with self.assertRaisesRegex(manage.OperationError, "TLS failed"):
            self.obj.complete()
        saved = json.loads(self.obj.state_path.read_text())
        self.assertFalse(saved["initialized"])
        self.assertIn("transaction", saved)
        self.assertNotIn(
            (True,), [call.args for call in self.obj.set_start.call_args_list]
        )
        self.assertIn("stop failed", (self.data / "logs/operations.log").read_text())

    def test_final_state_write_failure_disables_auto_and_keeps_journal(self):
        self.obj.start_services = Mock()
        self.obj.health = Mock()
        self.obj.set_start = Mock()
        self.obj.stop = Mock()
        save = self.obj.save

        def failed_save():
            if "transaction" not in self.obj.state:
                raise OSError("disk full")
            save()

        self.obj.save = failed_save
        with self.assertRaisesRegex(OSError, "disk full"):
            self.obj.complete()
        self.assertIn("transaction", json.loads(self.obj.state_path.read_text()))
        self.assertIn("transaction", self.obj.state)
        self.assertEqual(self.obj.set_start.call_args.args, (False,))

    def test_admin_bootstrap_after_repair_uses_existing_application(self):
        self.obj.storage_check = Mock()
        self.obj.start_services = Mock()
        self.obj.wait_database = Mock()
        self.obj.pg = Mock(return_value=SimpleNamespace(stdout="0\n"))
        self.obj.app = Mock()
        with patch.object(
            manage.getpass, "getpass", return_value="school-test-password"
        ):
            self.obj.admin("schooladmin")
        self.obj.app.assert_called_once_with(
            "scripts.create_admin",
            "--first-only",
            "--password-stdin",
            "schooladmin",
            input="school-test-password\n",
        )
        self.obj.start_services.assert_called_once_with(("postgres",))
        self.obj.wait_database.assert_called_once()
        self.obj.pg.return_value.stdout = "1\n"
        self.obj.app.reset_mock()
        with patch.object(manage.getpass, "getpass") as password:
            self.obj.admin("schooladmin")
        password.assert_not_called()
        self.obj.app.assert_not_called()

    def test_admin_never_runs_during_migration_or_recovery(self):
        self.obj.pg = Mock()
        self.obj.start_services = Mock()
        for phase in (
            "install",
            "migration",
            "repair",
            "finalize",
            "restore",
            "restored",
        ):
            self.obj.state["transaction"] = {"phase": phase}
            with self.assertRaisesRegex(manage.OperationError, "repair"):
                self.obj.admin("schooladmin")
        self.obj.pg.assert_not_called()
        self.obj.start_services.assert_not_called()

    def test_admin_rejects_invalid_password_before_application_call(self):
        self.obj.storage_check = Mock()
        self.obj.start_services = Mock()
        self.obj.wait_database = Mock()
        self.obj.pg = Mock(return_value=SimpleNamespace(stdout="0"))
        self.obj.app = Mock()
        for passwords in (
            ("short",),
            ("long-test-password", "different-test-password"),
        ):
            with (
                patch.object(manage.getpass, "getpass", side_effect=passwords),
                self.assertRaisesRegex(manage.OperationError, "Sandi"),
            ):
                self.obj.admin("schooladmin")
        self.obj.app.assert_not_called()

    def test_verified_patch_recovers_only_unfinished_original_install(self):
        source = self.path / "verified-patch"
        source.mkdir()
        manifest = dict(
            version="v1.1.1",
            format=1,
            platform="windows",
            architecture="amd64",
            postgres_major=18,
            upgrade_from_major=1,
        )
        (source / "release.json").write_text(json.dumps(manifest))
        (source / "manage.py").write_text("# verified fixture")
        self.obj.state.update(
            version="v1.1.0", initialized=False, transaction={"phase": "install"}
        )
        old = self.obj.release
        old.mkdir(parents=True)
        (old / "manage.py").write_text("# previous release")
        school = self.data / "precious"
        school.write_bytes(b"school data")
        config = self.obj.config.copy()
        self.obj.set_start = Mock()
        self.obj.stop = Mock()
        self.obj.recover_install(source, manifest)
        saved = json.loads(self.obj.state_path.read_text())
        self.assertEqual(saved["version"], "v1.1.1")
        self.assertEqual(saved["transaction"]["previous"], "v1.1.0")
        self.assertFalse(saved["initialized"])
        self.assertFalse(saved["autostart"])
        self.assertTrue((old / "manage.py").exists())
        self.assertTrue((self.obj.release / "manage.py").exists())
        self.assertEqual(school.read_bytes(), b"school data")
        self.assertEqual(config, self.obj.config)
        self.obj.resume_target = Mock()
        self.obj.repair()
        self.obj.resume_target.assert_called_once()

    def test_patch_recovery_rejects_other_transactions_and_versions(self):
        self.obj.set_start = Mock()
        self.obj.adopt_release = Mock()
        manifest = dict(version="v1.1.1", postgres_major=18, upgrade_from_major=1)
        for initialized, phase, old, target in (
            (True, "install", "v1.1.0", "v1.1.1"),
            (False, "migration", "v1.1.0", "v1.1.1"),
            (False, "restore", "v1.1.0", "v1.1.1"),
            (False, "restored", "v1.1.0", "v1.1.1"),
            (False, "install", "v1.1.1", "v1.1.0"),
            (False, "install", "v1.1.0", "v1.2.0"),
        ):
            self.obj.state.update(
                initialized=initialized, version=old, transaction={"phase": phase}
            )
            with self.assertRaises(manage.OperationError):
                self.obj.recover_install(self.path, dict(manifest, version=target))
        self.obj.set_start.assert_not_called()
        self.obj.adopt_release.assert_not_called()

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
