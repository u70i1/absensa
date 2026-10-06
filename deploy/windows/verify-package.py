"""Verify complete archive structure and its per-file build inventory."""

import json
import sys
from pathlib import Path

from package import digest, validate

root = Path(sys.argv[1])
validate(root)
expected = json.loads((root / "files.sha256.json").read_text())
actual = {
    p.relative_to(root).as_posix(): digest(p)
    for p in root.rglob("*")
    if p.is_file() and p.name != "files.sha256.json"
}
if actual != expected:
    raise SystemExit("Extracted release inventory/checksums do not match")
print("Windows release inventory and checksums verified")
