"""TLS regression tests; set CADDY_BINARY to also exercise a real local Caddy."""

import importlib.util
import contextlib
import io
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
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

    def test_http_error_status_survives_non_json_body(self):
        connection = Mock()
        connection.getresponse.return_value.status = 502
        connection.getresponse.return_value.read.return_value = (
            b"<html>Bad gateway</html>"
        )
        with (
            patch.object(manage.socket, "create_connection"),
            patch.object(
                manage.http.client, "HTTPSConnection", return_value=connection
            ),
        ):
            self.assertEqual(
                manage.https_health("school.test", 8443, Mock()), (502, None)
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
    def test_real_proxy_health_failure_recovery_and_ca_export(self):
        """Real sockets/Caddy/config/state; SCM and database are fixture adapters."""

        class Handler(BaseHTTPRequestHandler):
            status = 503

            def do_GET(self):
                self.send_response(self.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": self.status == 200}).encode())

            def log_message(self, *args):
                pass

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "web"))
        self.addCleanup(sys.path.pop, 0)
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.ExitStack() as stack,
        ):
            root = Path(directory)
            binary, data = root / "binary", root / "data"
            binary.mkdir()
            (data / "config").mkdir(parents=True)
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            stack.callback(server.server_close)
            stack.callback(thread.join, 5)
            stack.callback(server.shutdown)
            with socket.socket() as probe:
                probe.bind(("0.0.0.0", 0))
                port = probe.getsockname()[1]
            obj = manage.Installation(binary, data)
            obj.config = manage.new_config("absensa.test", port)
            obj.config.update(
                host="127.0.0.2",
                web_port=server.server_port,
                bridge_port=server.server_port,
            )
            obj.state = dict(
                format=1,
                version="v1.1.1",
                root=str(binary),
                data=str(data),
                initialized=False,
                transaction={"phase": "install"},
            )
            for role in ("scheduler", "backup"):
                stamp = data / "health" / role / f"absensa-{role}.heartbeat"
                stamp.parent.mkdir(parents=True)
                stamp.touch()
            obj.pg = Mock(return_value=SimpleNamespace(stdout="1"))
            obj.running = Mock(return_value=True)
            obj.set_start = Mock()
            obj.start_services = Mock()
            obj.stop = Mock()
            obj.health = lambda: manage.Installation.health(
                obj, attempts=10, interval=0.05
            )
            config = data / "config/Caddyfile"
            config.write_text(manage.caddyfile(obj.config), encoding="utf-8")
            env = dict(os.environ, **obj.environment("caddy"))
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
                    # Wait for TLS itself, then ensure real upstream 503 prevents finalization.
                    for attempt in range(100):
                        try:
                            context = ssl.create_default_context(
                                cafile=str(obj.ca_path)
                            )
                            self.assertEqual(
                                manage.https_health("127.0.0.2", port, context)[0], 503
                            )
                            break
                        except (OSError, AssertionError):
                            if process.poll() is not None or attempt == 99:
                                log.seek(0)
                                self.fail(log.read())
                            time.sleep(0.05)
                    with (
                        contextlib.redirect_stdout(io.StringIO()),
                        self.assertRaisesRegex(
                            manage.OperationError, "unexpected status 503"
                        ),
                    ):
                        obj.complete()
                    pending = json.loads(obj.state_path.read_text())
                    self.assertFalse(pending["initialized"])
                    self.assertFalse(pending["autostart"])
                    self.assertEqual(pending["transaction"]["phase"], "install")
                    self.assertFalse((data / "root-ca.crt").exists())
                    obj.stop.assert_called_once_with(manage.APPLICATION)
                    Handler.status = 200
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        obj.complete()
                    self.assertIn("SHA-256:", output.getvalue())
                    saved = json.loads(obj.state_path.read_text())
                    self.assertTrue(saved["initialized"] and saved["autostart"])
                    self.assertNotIn("transaction", saved)
                    self.assertEqual(
                        (data / "root-ca.crt").read_bytes(), obj.ca_path.read_bytes()
                    )
                    self.assertEqual(obj.set_start.call_args.args, (True,))
                    diagnostic = (data / "logs/operations.log").read_text()
                    self.assertIn("FINAL FAILURE", diagnostic)
                    self.assertIn("Health OK", diagnostic)
                finally:
                    process.terminate()
                    process.wait(timeout=10)

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
