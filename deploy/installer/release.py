"""Trust boundary shared by the bootstrap and installed manager (stdlib only)."""

import hashlib
import json
import re
import subprocess
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORY = "u70i1/absensa"
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
ARTIFACT = "absensa-linux-amd64.tar.gz"
MAX_DOWNLOAD = 32 * 1024 * 1024


class InstallError(Exception):
    pass


def download(url, destination, limit=MAX_DOWNLOAD):
    if not url.startswith("https://"):
        raise InstallError("Unduhan wajib menggunakan HTTPS.")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Absensa-installer",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            open(destination, "xb") as output,
        ):
            if not response.url.startswith("https://"):
                raise InstallError("Pengalihan unduhan tidak aman.")
            size = 0
            while data := response.read(1024 * 1024):
                size += len(data)
                if size > limit:
                    raise InstallError("Ukuran unduhan melampaui batas.")
                output.write(data)
    except (OSError, urllib.error.URLError) as exc:
        raise InstallError(
            "Unduhan gagal. Periksa internet, tanggal server, batas API GitHub, dan ketersediaan rilis stabil."
        ) from exc


def latest(directory):
    destination = Path(directory) / "latest.json"
    download(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
        destination,
        1024 * 1024,
    )
    release = json.loads(destination.read_text())
    tag = release.get("tag_name", "")
    if (
        release.get("draft", True)
        or release.get("prerelease", True)
        or not TAG.fullmatch(tag)
    ):
        raise InstallError("Rilis stabil dengan tag vMAJOR.MINOR.PATCH belum tersedia.")
    names = {asset["name"] for asset in release.get("assets", [])}
    if not {ARTIFACT, "SHA256SUMS", "provenance.jsonl"} <= names:
        raise InstallError(
            "Rilis belum lengkap. Pengelola perlu menerbitkan artefak dan bukti asal rilis."
        )
    return tag


def extract(archive, destination):
    """Reject links, devices, duplicates, traversal and decompression bombs."""
    destination = Path(destination)
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        names = set()
        size = 0
        for member in members:
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or member.name in names
                or not (member.isfile() or member.isdir())
            ):
                raise InstallError("Arsip rilis tidak aman.")
            names.add(member.name)
            size += member.size
            if size > MAX_DOWNLOAD or len(names) > 300:
                raise InstallError("Isi arsip rilis terlalu besar.")
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with source.extractfile(member) as stream, target.open("xb") as output:
                    output.write(stream.read())
                target.chmod(0o600)


def fetch(directory, tag=None):
    directory = Path(directory)
    tag = tag or latest(directory)
    if not TAG.fullmatch(tag):
        raise InstallError("Tag rilis tidak sah.")
    base = f"https://github.com/{REPOSITORY}/releases/download/{tag}"
    for name in (ARTIFACT, "SHA256SUMS", "provenance.jsonl"):
        download(f"{base}/{name}", directory / name)
    archive = directory / ARTIFACT
    expected = (directory / "SHA256SUMS").read_text().strip().split()
    if (
        len(expected) != 2
        or expected[1] != ARTIFACT
        or expected[0] != hashlib.sha256(archive.read_bytes()).hexdigest()
    ):
        raise InstallError(
            "Checksum rilis tidak cocok. Tidak ada kode unduhan yang dijalankan."
        )
    # The bundle is untrusted input; gh verifies Fulcio/Rekor and exact workflow/tag.
    result = subprocess.run(
        [
            "gh",
            "attestation",
            "verify",
            str(archive),
            "--bundle",
            str(directory / "provenance.jsonl"),
            "--repo",
            REPOSITORY,
            "--hostname",
            "github.com",
            "--cert-identity",
            f"https://github.com/{REPOSITORY}/.github/workflows/release.yml@refs/tags/{tag}",
            "--source-ref",
            f"refs/tags/{tag}",
            "--deny-self-hosted-runners",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise InstallError(
            "Bukti asal rilis tidak lolos verifikasi GitHub/Sigstore. Periksa versi gh, koneksi dan jam server; jangan lewati pemeriksaan ini."
        )
    destination = directory / "release"
    destination.mkdir(mode=0o700)
    extract(archive, destination)
    manifest = json.loads((destination / "release.json").read_text())
    if (
        manifest.get("version") != tag
        or manifest.get("format") != 1
        or manifest.get("architecture") != "amd64"
    ):
        raise InstallError("Manifest rilis tidak cocok dengan versi yang diminta.")
    for name in ("web", "backup", "whatsapp", "caddy", "postgres"):
        image = manifest.get("images", {}).get(name, "")
        if not re.fullmatch(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}", image):
            raise InstallError(
                "Rilis harus mengunci semua image dengan digest SHA-256."
            )
    return destination
