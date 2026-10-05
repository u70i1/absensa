"""The legacy setup must delegate to the verified release bootstrap."""
import unittest
from pathlib import Path


class LegacyEntryTests(unittest.TestCase):
    def test_no_legacy_account_reset_or_http_startup(self):
        source = Path(__file__).with_name("install.py").read_text()
        self.assertIn('"install.sh"', source)
        self.assertNotIn("create_admin", source)
        self.assertNotIn("http://", source)
