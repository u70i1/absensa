"""Create the small versioned deployment artifact after publishing pinned images."""

import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
from pathlib import Path

from release import ARTIFACT, REPOSITORY, TAG


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    if not TAG.fullmatch(args.version):
        raise SystemExit("Tag must use vMAJOR.MINOR.PATCH with no prerelease suffix.")
    images = {
        name: os.environ[f"{name.upper()}_IMAGE"]
        for name in ("web", "backup", "whatsapp", "caddy", "postgres")
    }
    if any(
        not re.fullmatch(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}", value)
        for value in images.values()
    ):
        raise SystemExit("All images must be pinned by digest.")
    args.output.mkdir(parents=True, exist_ok=True)
    staging = args.output / "release"
    staging.mkdir()
    for name in ("manage.py", "release.py", "compose.yml"):
        shutil.copyfile(Path(__file__).parent / name, staging / name)
    root = Path(__file__).resolve().parents[2]
    guide = (root / "deploy/README.md").read_text()
    # The installed artifact is not a repository checkout. Keep cross-document
    # links usable and tied to this release rather than pointing at absent files.
    for relative, repository_path in {
        "../RUNNING.md": "RUNNING.md",
        "RELEASING.md": "deploy/RELEASING.md",
        "BACKUPS.md": "deploy/BACKUPS.md",
        "INSTALLER-VALIDATION.md": "deploy/INSTALLER-VALIDATION.md",
    }.items():
        guide = guide.replace(
            f"]({relative})",
            f"](https://github.com/{REPOSITORY}/blob/{args.version}/{repository_path})",
        )
    (staging / "PANDUAN.md").write_text(guide)
    (staging / "release.json").write_text(
        json.dumps(
            {
                "format": 1,
                "version": args.version,
                "architecture": "amd64",
                "upgrade_from_major": int(args.version.split(".")[0][1:]),
                "source_commit": os.environ.get("GITHUB_SHA", ""),
                "images": images,
            },
            indent=2,
        )
        + "\n"
    )
    archive = args.output / ARTIFACT
    with tarfile.open(archive, "w:gz") as output:
        for item in sorted(staging.iterdir()):
            output.add(item, arcname=item.name)
    (args.output / "SHA256SUMS").write_text(
        hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + ARTIFACT + "\n"
    )


if __name__ == "__main__":
    main()
