import base64
import hashlib
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import manage
import package_release
import release


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def installation(self):
        (self.root / "backups").mkdir()
        config = {
            "INSTALL_DIR": str(self.root),
            "HOSTNAME": "absensa.test",
            "TLS_MODE": "internal",
            "HTTPS_PORT": "8443",
            "BIND_IP": "127.0.0.1",
            "PUBLIC_URL": "https://absensa.test:8443",
            "TIMEZONE": "Asia/Jakarta",
            "POSTGRES_PASSWORD": "a" * 64,
            "WHATSAPP_BRIDGE_TOKEN": "b" * 64,
            "BACKUP_ENCRYPTION_KEY": base64.b64encode(b"k" * 32).decode(),
            "BACKUP_DIR": str(self.root / "backups"),
            "FULL_BACKUP_KEEP": "7",
            "BACKUP_TIMES": "10:00,17:00",
            "BACKUP_KEEP_DAILY": "14",
        }
        manage.env_write(self.root / "production.env", config)
        manage.atomic(
            self.root / "state.json",
            json.dumps(
                {
                    "format": 1,
                    "version": "v1.0.0",
                    "project": "absensa-123456789abc",
                    "initialized": True,
                }
            ),
        )
        obj = manage.Installation(self.root)
        obj.ensure_storage = Mock()
        obj.release.mkdir(parents=True)
        (obj.release / "compose.yml").write_text("services: {}")
        for name in ("manage.py", "release.py"):
            (obj.release / name).write_text("# test fixture\n")
        (obj.release / "release.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "version": "v1.0.0",
                    "architecture": "amd64",
                    "images": {
                        name: "example/" + name + "@sha256:" + "a" * 64
                        for name in ("web", "backup", "whatsapp", "caddy", "postgres")
                    },
                }
            )
        )
        (self.root / "Caddyfile").write_text(manage.caddyfile(config))
        return obj

    def test_secret_file_permissions_and_roundtrip(self):
        obj = self.installation()
        self.assertEqual((self.root / "production.env").stat().st_mode & 0o777, 0o600)
        self.assertEqual(manage.env_read(obj.config_path), obj.config)

    def test_network_pool_exhaustion_has_safe_actionable_error(self):
        result = Mock(
            returncode=1,
            stderr="all predefined address pools have been fully subnetted\nprivate-secret",
        )
        with patch.object(manage.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(release.InstallError, "subnet") as error:
                manage.run(["docker", "compose", "up"])
        self.assertNotIn("private-secret", str(error.exception))

    def test_missing_persistent_volume_stops_without_creating_empty_storage(self):
        obj = self.installation()
        with (
            patch.object(manage, "run", return_value=Mock(returncode=1)) as command,
            patch.object(obj, "compose") as compose,
        ):
            with self.assertRaisesRegex(release.InstallError, "Volume data"):
                manage.Installation.ensure_storage(obj)
        compose.assert_not_called()
        self.assertEqual(command.call_args.args[0][:3], ["docker", "volume", "inspect"])
        self.assertEqual(len(command.call_args.args[0]), 7)

    def test_env_injection_rejected(self):
        for value in ("x\ny=z", "${EVIL}", "a#b", 'a"b', "a'b", "a\\b"):
            with self.subTest(value=value), self.assertRaises(release.InstallError):
                manage.env_write(self.root / "env", {"VALUE": value})

    def test_hostname_injection_and_unsafe_ip(self):
        for value in (
            "foo\nbar",
            "a.com {",
            "https://a.com",
            "127.0.0.1",
            "0.0.0.0",
            "a..com",
            "-a.com",
            "a.com:443",
        ):
            with self.subTest(value=value), self.assertRaises(release.InstallError):
                manage.hostname(value)
        self.assertEqual(manage.hostname("192.168.1.10"), "192.168.1.10")
        self.assertEqual(
            manage.hostname("absensa.sekolah.sch.id"), "absensa.sekolah.sch.id"
        )

    def test_compose_always_explicit_project_and_file(self):
        obj = self.installation()
        with patch.object(manage, "run", return_value=Mock(stdout="")) as run:
            obj.compose("stop", "web")
        args = run.call_args.args[0]
        self.assertIn("absensa-123456789abc", args)
        self.assertIn(str(obj.release / "compose.yml"), args)
        self.assertNotIn("down", args)

    def test_existing_menu_cancel_performs_no_dependency_or_network_work(self):
        self.installation()
        with (
            patch("sys.argv", ["manage.py", "--directory", str(self.root)]),
            patch.object(manage, "ask", return_value="3"),
            patch.object(manage, "host_check") as host,
        ):
            manage.main()
        host.assert_not_called()

    def test_migration_journal_blocks_start_and_backup(self):
        obj = self.installation()
        obj.state["transaction"] = {"phase": "migration"}
        with patch.object(obj, "compose") as compose:
            with self.assertRaises(release.InstallError):
                obj.start()
            with self.assertRaises(release.InstallError):
                obj.snapshot()
        compose.assert_not_called()

    def test_failed_backup_blocks_update_and_restores_previous_services(self):
        obj = self.installation()

        def compose(*args, **kwargs):
            if "app.jobs.backups" in args:
                raise release.InstallError("gagal")
            return Mock(stdout="web\nscheduler\ncaddy\n")

        with (
            patch.object(obj, "ensure_no_orphans"),
            patch.object(obj, "compose", side_effect=compose) as commands,
        ):
            with self.assertRaises(release.InstallError):
                obj.snapshot(resume=False)
        self.assertIn(
            unittest.mock.call("start", "web", "scheduler", "caddy"),
            commands.call_args_list,
        )
        self.assertNotIn("transaction", obj.state)
        self.assertFalse(
            any("migrate" in call.args for call in commands.call_args_list)
        )

    def test_backup_rejects_running_maintenance_before_stopping_services(self):
        obj = self.installation()
        with (
            patch.object(
                obj,
                "ensure_no_orphans",
                side_effect=release.InstallError("masih berjalan"),
            ),
            patch.object(obj, "compose") as compose,
        ):
            with self.assertRaises(release.InstallError):
                obj.snapshot()
        compose.assert_not_called()
        self.assertNotIn("transaction", obj.state)

    def test_initial_migration_finishes_backup_permissions_before_database_start(self):
        obj = self.installation()
        obj.state["initialized"] = False
        with (
            patch.object(obj, "ensure_no_orphans"),
            patch.object(obj, "compose") as compose,
        ):
            obj.migrate()
        commands = [call.args for call in compose.call_args_list]
        self.assertIn("os.chown('/app/backups',10001,10001)", commands[0][-1])
        self.assertEqual(commands[1][0], "up")
        obj.state["initialized"] = True
        with patch.object(obj, "compose") as compose:
            obj.prepare_backup_directory()
        compose.assert_not_called()

    def test_failed_migration_keeps_target_and_recovery_journal(self):
        obj = self.installation()
        obj.state["transaction"] = {
            "phase": "migration",
            "target": "v1.0.1",
            "previous": "v1.0.0",
            "backup": "/safe/archive.absfull",
        }
        with (
            patch.object(obj, "write_runtime"),
            patch.object(obj, "migrate", side_effect=release.InstallError("gagal")),
            patch.object(obj, "compose") as compose,
        ):
            with self.assertRaises(release.InstallError):
                obj.finish_update()
        saved = json.loads(obj.state_path.read_text())
        self.assertEqual(saved["version"], "v1.0.1")
        self.assertEqual(saved["transaction"]["backup"], "/safe/archive.absfull")
        compose.assert_not_called()

    def test_repair_interrupted_backup_restarts_only_previous_services(self):
        obj = self.installation()
        obj.state["transaction"] = {"phase": "backup", "resume": ["web"]}
        with (
            patch.object(obj, "compose") as compose,
            patch.object(obj, "write_runtime"),
            patch.object(obj, "ensure_no_orphans"),
            patch.object(obj, "pull"),
            patch.object(obj, "start"),
        ):
            obj.repair()
        compose.assert_called_once_with("start", "web")

    def test_admin_existing_not_prompted_or_reset(self):
        obj = self.installation()
        with (
            patch.object(obj, "compose", return_value=Mock(stdout="1\n")) as compose,
            patch.object(manage, "yes") as prompt,
        ):
            obj.initialize_admin()
        prompt.assert_not_called()
        self.assertEqual(compose.call_count, 1)

    def test_admin_password_only_in_stdin_and_first_only(self):
        obj = self.installation()
        with (
            patch.object(obj, "compose", return_value=Mock(stdout="0\n")) as compose,
            patch.object(manage, "yes", return_value=True),
            patch.object(manage, "ask", return_value="admin"),
            patch.object(
                manage.getpass, "getpass", return_value="private password 123"
            ),
        ):
            obj.initialize_admin()
        call = compose.call_args
        self.assertIn("--first-only", call.args)
        self.assertNotIn("private password 123", call.args)
        self.assertEqual(call.kwargs["data"], "private password 123\n")

    def test_caddy_dns_token_never_written_to_caddyfile(self):
        obj = self.installation()
        obj.config.update(TLS_MODE="cloudflare", CF_API_TOKEN="private-token")
        result = manage.caddyfile(obj.config)
        self.assertIn("{env.CF_API_TOKEN}", result)
        self.assertNotIn("private-token", result)
        self.assertIn("unix//run/absensa/web.sock", result)
        self.assertIn("disable_redirects", result)

    def test_no_start_choice_never_starts_database(self):
        source = self.root / "source"
        source.mkdir()
        (source / "release.json").write_text(json.dumps({"version": "v1.0.0"}))
        root = self.root / "installed"
        answers = ["1", "absensa.test", "1", str(root / "backups"), "10:00,17:00", "14"]
        with (
            patch.object(manage, "ask", side_effect=answers),
            patch.object(manage, "choose_port", return_value=8443),
            patch.object(manage, "yes", side_effect=[True, False]),
            patch.object(manage.Installation, "write_runtime"),
            patch.object(manage.Installation, "pull"),
            patch.object(manage.Installation, "compose") as compose,
            patch.object(manage.Installation, "start") as start,
        ):
            manage.install_release(source, root)
        start.assert_not_called()
        self.assertFalse(any("up" in call.args for call in compose.call_args_list))
        self.assertFalse(json.loads((root / "state.json").read_text())["initialized"])

    def test_restore_refuses_existing_destination(self):
        obj = self.installation()
        with self.assertRaises(release.InstallError):
            manage.restore(obj, "/unused", "/unused", self.root)

    def test_failed_migration_allows_isolated_recovery_without_starting_source(self):
        obj = self.installation()
        obj.state["transaction"] = {"phase": "migration"}
        key = self.root / "recovery.key"
        key.write_text(obj.config["BACKUP_ENCRYPTION_KEY"])
        with (
            patch.object(manage, "yes", return_value=False) as prompt,
            patch.object(obj, "compose") as compose,
        ):
            manage.restore(obj, "/unused", key, self.root / "recovered")
        prompt.assert_called_once()
        compose.assert_not_called()
        self.assertFalse((self.root / "recovered").exists())
        self.assertEqual(obj.state["transaction"]["phase"], "migration")

    def test_repair_recovers_missing_manager_and_launcher(self):
        obj = self.installation()
        intact = self.root / "verified"
        import shutil

        shutil.copytree(obj.release, intact)
        (obj.release / "manage.py").unlink()
        with (
            patch.object(manage, "fetch", return_value=intact) as fetch,
            patch.object(obj, "ensure_no_orphans"),
            patch.object(obj, "write_runtime"),
            patch.object(obj, "pull"),
            patch.object(obj, "start"),
        ):
            obj.repair()
        self.assertEqual(fetch.call_args.args[1], "v1.0.0")
        self.assertTrue((obj.release / "manage.py").is_file())
        self.assertEqual((self.root / "absensa").stat().st_mode & 0o777, 0o700)

    def test_start_refreshes_caddy_bind_mount_before_https_check(self):
        obj = self.installation()
        with (
            patch.object(obj, "write_runtime"),
            patch.object(obj, "migrate"),
            patch.object(obj, "check_https") as check,
            patch.object(obj, "compose") as compose,
        ):
            obj.start()
        self.assertEqual(
            compose.call_args_list[0].args, ("up", "-d", "--force-recreate", "caddy")
        )
        check.assert_called_once()

    def test_private_directory_rejects_symlink(self):
        (self.root / "link").symlink_to(self.root)
        with self.assertRaises(release.InstallError):
            manage.private_directory(self.root / "link")

    def test_remote_docker_environment_rejected(self):
        with (
            patch.dict(os.environ, {"DOCKER_HOST": "ssh://school-server"}),
            self.assertRaisesRegex(release.InstallError, "DOCKER_HOST"),
        ):
            manage.host_check(self.root)

    def test_downward_version_comparison(self):
        self.assertGreater(
            manage.version_tuple("v1.10.0"), manage.version_tuple("v1.9.0")
        )
        for value in ("latest", "v1.0.0-rc1", "v01.0.0", "main"):
            with self.assertRaises(release.InstallError):
                manage.version_tuple(value)

    def test_occupied_docker_port_detected_even_without_socket(self):
        with (
            patch.object(manage, "ask", side_effect=["443", "8443"]),
            patch.object(
                manage, "run", return_value=Mock(stdout="0.0.0.0:443->443/tcp")
            ),
            patch.object(manage.socket, "socket") as sock,
        ):
            self.assertEqual(manage.choose_port(), 8443)
        sock.return_value.__enter__.return_value.bind.assert_called_once_with(
            ("0.0.0.0", 8443)
        )

    def test_generated_bootstrap_matches_shared_verifier(self):
        directory = Path(__file__).parent
        expected = (
            (directory / "bootstrap.sh.in")
            .read_text()
            .replace(
                "# SHARED_RELEASE_VERIFIER", (directory / "release.py").read_text()
            )
        )
        self.assertEqual((directory.parents[1] / "install.sh").read_text(), expected)

    def test_saved_configuration_beats_shell_environment(self):
        obj = self.installation()
        with (
            patch.dict(
                os.environ, {"POSTGRES_PASSWORD": "wrong", "WEB_IMAGE": "evil:latest"}
            ),
            patch.object(
                manage.subprocess, "run", return_value=Mock(returncode=0, stdout="")
            ) as execute,
        ):
            obj.compose("config", "--quiet")
        passed = execute.call_args.kwargs["env"]
        self.assertFalse("POSTGRES_PASSWORD" in passed)
        self.assertFalse("WEB_IMAGE" in passed)

    def test_restored_installation_cannot_start_via_repair(self):
        obj = self.installation()
        obj.state["restored_isolated"] = True
        with (
            patch.object(obj, "ensure_no_orphans"),
            patch.object(obj, "compose") as compose,
        ):
            with self.assertRaises(release.InstallError):
                obj.repair()
            with self.assertRaises(release.InstallError):
                obj.start()
        compose.assert_not_called()

    def test_backup_directory_cannot_take_ownership_of_installation(self):
        source = self.root / "release"
        source.mkdir()
        target = self.root / "new-install"
        with (
            patch.object(
                manage, "ask", side_effect=["1", "absensa.test", "1", str(target)]
            ),
            patch.object(manage, "choose_port", return_value=8443),
            self.assertRaises(release.InstallError),
        ):
            manage.install_release(source, target)
        self.assertFalse(target.exists())

    def test_running_orphan_blocks_repair(self):
        obj = self.installation()
        with (
            patch.object(manage, "run", return_value=Mock(stdout="container-id\n")),
            patch.object(obj, "compose") as compose,
            self.assertRaises(release.InstallError),
        ):
            obj.repair()
        compose.assert_not_called()


class ReleaseTests(unittest.TestCase):
    def test_package_pins_images_checksum_and_guide_links_to_release(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            images = {
                name.upper() + "_IMAGE": "example/" + name + "@sha256:" + "a" * 64
                for name in ("web", "backup", "whatsapp", "caddy", "postgres")
            }
            with (
                patch.dict(os.environ, images),
                patch(
                    "sys.argv", ["package_release.py", "v1.2.3", "--output", directory]
                ),
            ):
                package_release.main()
            archive = destination / release.ARTIFACT
            self.assertEqual(
                (destination / "SHA256SUMS").read_text().split()[0],
                hashlib.sha256(archive.read_bytes()).hexdigest(),
            )
            guide = (destination / "release/PANDUAN.md").read_text()
            self.assertNotIn("](../RUNNING.md)", guide)
            self.assertIn(
                "https://github.com/u70i1/absensa/blob/v1.2.3/deploy/BACKUPS.md", guide
            )
            manifest = json.loads((destination / "release/release.json").read_text())
            self.assertEqual(manifest["version"], "v1.2.3")
            self.assertTrue(
                all("@sha256:" in image for image in manifest["images"].values())
            )

    def test_latest_rejects_drafts_prerelease_and_missing_assets(self):
        for values in (
            {"draft": True},
            {"prerelease": True},
            {"tag_name": "main"},
            {"assets": []},
        ):
            data = {
                "draft": False,
                "prerelease": False,
                "tag_name": "v1.2.3",
                "assets": [
                    {"name": x}
                    for x in (release.ARTIFACT, "SHA256SUMS", "provenance.jsonl")
                ],
            }
            data.update(values)
            with (
                tempfile.TemporaryDirectory() as d,
                patch.object(
                    release,
                    "download",
                    side_effect=lambda url, p, limit: p.write_text(json.dumps(data)),
                ),
                self.assertRaises(release.InstallError),
            ):
                release.latest(d)

    def test_archive_rejects_traversal_links_devices_and_duplicate_names(self):
        for kind in (
            "traversal",
            "absolute",
            "symlink",
            "hardlink",
            "device",
            "duplicate",
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                p = Path(d)
                source = p / "input.tar.gz"
                with tarfile.open(source, "w:gz") as archive:
                    item = tarfile.TarInfo(
                        "../escape"
                        if kind == "traversal"
                        else "/escape"
                        if kind == "absolute"
                        else "x"
                    )
                    if kind == "symlink":
                        item.type = tarfile.SYMTYPE
                        item.linkname = "/etc/passwd"
                    if kind == "hardlink":
                        item.type = tarfile.LNKTYPE
                        item.linkname = "/etc/passwd"
                    if kind == "device":
                        item.type = tarfile.CHRTYPE
                    archive.addfile(item)
                    if kind == "duplicate":
                        archive.addfile(item)
                with self.assertRaises(release.InstallError):
                    release.extract(source, p / "output")

    def test_rejected_attestation_never_extracts_or_executes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)

            def download(url, path):
                if path.name == release.ARTIFACT:
                    path.write_bytes(b"archive")
                elif path.name == "SHA256SUMS":
                    path.write_text(
                        hashlib.sha256(b"archive").hexdigest() + "  " + release.ARTIFACT
                    )
                else:
                    path.write_text("{}")

            with (
                patch.object(release, "download", side_effect=download),
                patch.object(
                    release.subprocess, "run", return_value=Mock(returncode=1)
                ) as verify,
                patch.object(release, "extract") as extract,
                self.assertRaises(release.InstallError),
            ):
                release.fetch(p, "v1.2.3")
            extract.assert_not_called()
            args = verify.call_args.args[0]
            self.assertIn("--deny-self-hosted-runners", args)
            self.assertIn(
                "https://github.com/u70i1/absensa/.github/workflows/release.yml@refs/tags/v1.2.3",
                args,
            )

    def test_checksum_mismatch_blocks_verifier(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(
                release, "download", side_effect=lambda url, p: p.write_text("bad")
            ),
            patch.object(release.subprocess, "run") as verify,
            self.assertRaises(release.InstallError),
        ):
            release.fetch(d, "v1.0.0")
        verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
