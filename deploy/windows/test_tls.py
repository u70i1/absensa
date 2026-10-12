"""TLS regression tests; set CADDY_BINARY to also exercise a real local Caddy."""

import importlib.util
import os
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    "manage", Path(__file__).with_name("manage.py")
)
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class ProbeTests(unittest.TestCase):
    def test_destination_and_verified_identity(self):
        for host, destination in (
            ("192.168.0.10", "192.168.0.10"),
            ("absensa.school.test", "127.0.0.1"),
        ):
            with self.subTest(host=host):
                context = Mock()
                connection = Mock()
                connection.getresponse.return_value.status = 200
                connection.getresponse.return_value.read.return_value = b'{"ok":true}'
                with (
                    patch.object(manage.socket, "create_connection") as connect,
                    patch.object(
                        manage.http.client, "HTTPSConnection", return_value=connection
                    ),
                ):
                    self.assertEqual(
                        manage.https_health(host, 8443, context), (200, {"ok": True})
                    )
                connect.assert_called_once_with((destination, 8443), timeout=5)
                self.assertEqual(
                    context.wrap_socket.call_args.kwargs, {"server_hostname": host}
                )
                connection.close.assert_called_once()

    def test_handshake_failure_closes_connections(self):
        context = Mock()
        context.wrap_socket.side_effect = ssl.SSLError("handshake failed")
        with (
            patch.object(manage.socket, "create_connection") as connect,
            patch.object(manage.http.client, "HTTPSConnection") as connection,
            self.assertRaises(ssl.SSLError),
        ):
            manage.https_health("192.168.0.10", 8443, context)
        connect.return_value.__exit__.assert_called_once()
        connection.return_value.close.assert_called_once()


@unittest.skipUnless(
    os.environ.get("CADDY_BINARY"), "Set CADDY_BINARY for real TLS regression"
)
class CaddyTests(unittest.TestCase):
    def test_real_ip_dns_and_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with socket.socket() as probe:
                probe.bind(("0.0.0.0", 0))
                port = probe.getsockname()[1]
            config = root / "Caddyfile"
            config.write_text(
                "{\n auto_https disable_redirects\n admin off\n skip_install_trust\n}\n"
                f"https://127.0.0.2:{port}, https://absensa.test:{port} {{\n"
                ' tls internal\n respond /health `{"ok":true}` 200\n}\n',
                encoding="utf-8",
            )
            env = dict(
                os.environ,
                XDG_DATA_HOME=str(root / "data"),
                XDG_CONFIG_HOME=str(root / "config"),
            )
            with (root / "caddy.log").open("w+") as log:
                process = subprocess.Popen(
                    [
                        os.environ["CADDY_BINARY"],
                        "run",
                        "--config",
                        str(config),
                        "--adapter",
                        "caddyfile",
                    ],
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                try:
                    ca = root / "data/caddy/pki/authorities/local/root.crt"
                    for attempt in range(100):
                        try:
                            context = ssl.create_default_context(cafile=str(ca))
                            self.assertEqual(
                                manage.https_health("127.0.0.2", port, context),
                                (200, {"ok": True}),
                            )
                            self.assertEqual(
                                manage.https_health("absensa.test", port, context),
                                (200, {"ok": True}),
                            )
                            break
                        except (OSError, AssertionError):
                            if process.poll() is not None or attempt == 99:
                                log.seek(0)
                                self.fail(log.read())
                            time.sleep(0.1)
                    # Reproduce the original IP-over-loopback handshake failure.
                    with self.assertRaises(ssl.SSLError):
                        with socket.create_connection(("127.0.0.1", port)) as sock:
                            context.wrap_socket(sock, server_hostname="127.0.0.2")
                    # A trusted CA alone cannot bypass the IP SAN check.
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        with socket.create_connection(("127.0.0.2", port)) as sock:
                            context.wrap_socket(sock, server_hostname="127.0.0.3")
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        manage.https_health(
                            "127.0.0.2", port, ssl.create_default_context()
                        )
                finally:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
