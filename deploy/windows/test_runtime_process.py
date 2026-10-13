"""Actual process checks on POSIX; Windows console/WinSW delivery still needs CI."""

import os
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVER = """
import sys
sys.path.insert(0, sys.argv[1])
from runtime import run_child
raise SystemExit(run_child([sys.executable, '-u', '-c', sys.argv[2]], sys.argv[3]))
"""


@unittest.skipUnless(
    os.name == "posix", "POSIX process group test; use native smoke for WinSW"
)
class RuntimeProcessTests(unittest.TestCase):
    def test_interrupt_waits_for_real_child_cleanup_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            child = """
import signal, time
from pathlib import Path
def stop(*args):
    Path('child-cleaned-up').write_text('done')
    raise SystemExit(0)
signal.signal(signal.SIGINT, stop)
print('READY', flush=True)
while True:
    time.sleep(0.1)
"""
            process = subprocess.Popen(
                [sys.executable, "-u", "-c", DRIVER, str(HERE), child, directory],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                self.assertTrue(
                    select.select([process.stdout], [], [], 10)[0],
                    "Child never became ready",
                )
                self.assertEqual(process.stdout.readline().strip(), "READY")
                os.killpg(process.pid, signal.SIGINT)
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(
                    (Path(directory) / "child-cleaned-up").read_text(), "done"
                )
                self.assertIn("Service stop requested", stdout)
                self.assertNotIn("Traceback", stderr)
                self.assertNotIn("KeyboardInterrupt", stderr)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=10)

    def test_real_child_crash_remains_visible_and_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-u",
                    "-c",
                    DRIVER,
                    str(HERE),
                    "raise RuntimeError('real child crash fixture')",
                    directory,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("RuntimeError: real child crash fixture", result.stderr)
        self.assertIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
