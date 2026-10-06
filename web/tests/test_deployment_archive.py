"""Validate the extraction boundary used by full deployment recovery."""

import io
import os
import stat
import tarfile

import pytest
from app.jobs.deployment_archive import add_tree, publish_snapshot, safe_unpack


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/outside",
        "nested/../../outside",
        "C:/outside",
        "nested\\outside",
        "file:stream",
        "NUL.txt",
        "a.",
        "a ",
    ],
)
def test_restore_rejects_path_escape(tmp_path, name):
    source = tmp_path / "archive.tar"
    with tarfile.open(source, "w") as archive:
        member = tarfile.TarInfo(name)
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    destination = tmp_path / "restore"
    destination.mkdir()
    with pytest.raises(ValueError, match="Arsip tidak aman"):
        safe_unpack(source, destination)
    assert not list(destination.rglob("*"))
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE]
)
def test_restore_rejects_links_and_special_files(tmp_path, kind):
    source = tmp_path / "archive.tar"
    with tarfile.open(source, "w") as archive:
        member = tarfile.TarInfo("unsafe")
        member.type = kind
        member.linkname = "../../outside"
        archive.addfile(member)
    destination = tmp_path / "restore"
    destination.mkdir()
    with pytest.raises(ValueError, match="Arsip tidak aman"):
        safe_unpack(source, destination)
    assert not list(destination.iterdir())


def test_restore_rejects_duplicate_without_overwriting_first_file(tmp_path):
    source = tmp_path / "archive.tar"
    with tarfile.open(source, "w") as archive:
        for content in (b"original", b"replacement"):
            member = tarfile.TarInfo("config/state.json")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    destination = tmp_path / "restore"
    destination.mkdir()
    with pytest.raises(ValueError, match="Arsip tidak aman"):
        safe_unpack(source, destination)
    assert (destination / "config/state.json").read_bytes() == b"original"


def test_snapshot_omits_chromium_process_links_and_restores_nested_data(tmp_path):
    profile = tmp_path / "profile"
    (profile / "nested").mkdir(parents=True)
    (profile / "nested/session").write_bytes(b"session fixture")
    (profile / "SingletonLock").symlink_to("/unavailable-process-lock")
    source = tmp_path / "archive.tar"
    with tarfile.open(source, "w") as archive:
        add_tree(archive, profile, "whatsapp")
    destination = tmp_path / "restore"
    destination.mkdir()
    safe_unpack(source, destination)
    assert (destination / "whatsapp/nested/session").read_bytes() == b"session fixture"
    assert not (destination / "whatsapp/SingletonLock").is_symlink()


def test_snapshot_rejects_other_symlinks(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "unexpected").symlink_to("/outside")
    with (
        tarfile.open(tmp_path / "archive.tar", "w") as archive,
        pytest.raises(ValueError, match="Berkas khusus"),
    ):
        add_tree(archive, profile, "whatsapp")


def test_snapshot_publication_persists_directory_entry(tmp_path, monkeypatch):
    partial, destination = tmp_path / "archive.partial", tmp_path / "archive.absfull"
    partial.write_bytes(b"encrypted fixture")
    synced = []
    actual_fsync = os.fsync

    def checked_fsync(fd):
        assert stat.S_ISDIR(os.fstat(fd).st_mode)
        assert destination.read_bytes() == b"encrypted fixture"
        actual_fsync(fd)
        synced.append(True)

    monkeypatch.setattr(os, "fsync", checked_fsync)
    publish_snapshot(partial, destination)
    assert synced
    assert not partial.exists()


def test_snapshot_does_not_report_success_if_directory_sync_fails(
    tmp_path, monkeypatch
):
    partial, destination = tmp_path / "archive.partial", tmp_path / "archive.absfull"
    partial.write_bytes(b"encrypted fixture")

    def fail_sync(fd):
        raise OSError("simulated storage failure")

    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(OSError, match="storage failure"):
        publish_snapshot(partial, destination)
    assert destination.read_bytes() == b"encrypted fixture"
