"""Safety checks for the optional setup wizard."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import install
from configure import write_config


class InstallerSafetyTests(unittest.TestCase):
    def test_existing_database_needs_explicit_resume_and_keeps_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "production.env"
            write_config(config, 8088)
            original = config.read_bytes()
            with (
                patch.object(install, "CONFIG", config),
                patch.object(install, "MARKER", Path(directory) / "initialized.json"),
                patch.object(install, "inspect_host"),
                patch.object(install, "any_existing_data", return_value=True),
                patch.object(install, "run_step") as run_step,
                patch("sys.argv", ["install.py"]),
                self.assertRaisesRegex(install.SetupError, "--resume"),
            ):
                install.main()
            self.assertEqual(config.read_bytes(), original)
            run_step.assert_not_called()

    def test_admin_password_uses_stdin_only(self):
        result = Mock(returncode=0)
        with patch.object(install.subprocess, "run", return_value=result) as run:
            install.create_admin("admin", "a private password")
        arguments = run.call_args.args[0]
        self.assertNotIn("a private password", " ".join(arguments))
        self.assertEqual(run.call_args.kwargs["input"], "a private password\n")
        self.assertIn("--password-stdin", arguments)

    def test_completed_install_cannot_be_restarted_with_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "initialized.json"
            marker.write_text("{}")
            with (
                patch.object(install, "MARKER", marker),
                patch.object(install, "inspect_host"),
                patch.object(install, "run_step") as run_step,
                patch("sys.argv", ["install.py", "--resume"]),
            ):
                install.main()
            run_step.assert_not_called()
