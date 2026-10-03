"""Keep the standalone bootstrap verifier identical to the updater verifier."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = Path(__file__).parent
content = (
    (source / "bootstrap.sh.in")
    .read_text()
    .replace("# SHARED_RELEASE_VERIFIER", (source / "release.py").read_text())
)
(ROOT / "install.sh").write_text(content)
(ROOT / "install.sh").chmod(0o755)
