"""Exercise the real Bash entry point through a pipe and a controlling terminal."""

import os
import pty
import select
import signal
import tempfile
import time
import unittest
from pathlib import Path


class PipeTests(unittest.TestCase):
    def test_prompts_use_tty_and_cancel_reuses_existing_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "bin"
            binary.mkdir()
            # Simulate supported OS metadata without changing the host.
            shim = binary / "sed"
            shim.write_text(
                '#!/bin/bash\ncase "$2" in *VERSION_ID*) echo 24.04;; *ID=*) echo ubuntu;; *) exec /usr/bin/sed "$@";; esac\n'
            )
            shim.chmod(0o755)
            site = root / "installed"
            (site / "releases/v1.0.0").mkdir(parents=True)
            (site / "releases/v1.0.0/manage.py").write_text("# fixture")
            (site / "state.json").write_text('{"version":"v1.0.0"}')
            launcher = site / "absensa"
            launcher.write_text(
                '#!/bin/bash\nprintf "MENU_FIXTURE\\n"; read -r answer </dev/tty; [ "$answer" = 3 ] && printf "CANCEL_OK\\n"\n'
            )
            launcher.chmod(0o755)
            script = Path(__file__).resolve().parents[2] / "install.sh"
            pid, fd = pty.fork()
            if pid == 0:
                os.environ["PATH"] = str(binary) + ":" + os.environ["PATH"]
                # Fixture paths come only from TemporaryDirectory/repository.
                os.execl(
                    "/bin/bash",
                    "bash",
                    "-c",
                    'cat "$1" | bash -s -- "$2"',
                    "test",
                    str(script),
                    str(site),
                )
            output = b""
            answered = False
            canceled = False
            try:
                end = time.monotonic() + 10
                while time.monotonic() < end:
                    readable, _, _ = select.select([fd], [], [], 0.1)
                    if readable:
                        try:
                            block = os.read(fd, 4096)
                        except OSError:
                            break
                        if not block:
                            break
                        output += block
                    if b"Direktori instalasi" in output and not answered:
                        os.write(fd, b"\n")
                        answered = True
                    if b"MENU_FIXTURE" in output and not canceled:
                        os.write(fd, b"3\n")
                        canceled = True
                    if b"CANCEL_OK" in output:
                        break
                self.assertIn(b"CANCEL_OK", output, output.decode(errors="replace"))
                self.assertNotIn(b"Mencari rilis", output)
            finally:
                os.close(fd)
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)


if __name__ == "__main__":
    unittest.main()
