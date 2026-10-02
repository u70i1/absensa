import base64
import tempfile
import unittest
from pathlib import Path

from configure import write_config


class ConfigureTests(unittest.TestCase):
    def test_independent_secrets_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "production.env"
            write_config(path, 8088)
            original = path.read_text()
            values = dict(
                line.split("=", 1)
                for line in original.splitlines()
                if line and not line.startswith("#")
            )
            password = values["POSTGRES_PASSWORD"]
            token = values["WHATSAPP_BRIDGE_TOKEN"]
            self.assertRegex(password, r"^[0-9a-f]{64}$")
            self.assertRegex(token, r"^[0-9a-f]{64}$")
            self.assertNotEqual(password, token)
            self.assertEqual(len(base64.b64decode(values["BACKUP_ENCRYPTION_KEY"])), 32)
            with self.assertRaises(FileExistsError):
                write_config(path, 8090)
            self.assertEqual(path.read_text(), original)

    def test_invalid_port_does_not_create_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "production.env"
            for port in (0, 80, 65536):
                with self.assertRaises(ValueError):
                    write_config(path, port)
                self.assertFalse(path.exists())

    def test_selected_timezone_is_saved_without_reducing_secret_strength(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "production.env"
            write_config(path, 8090, "Asia/Makassar")
            self.assertIn("TIMEZONE=Asia/Makassar\n", path.read_text())
            with self.assertRaises(ValueError):
                write_config(Path(directory) / "invalid.env", 8090, "Etc/Unknown")
