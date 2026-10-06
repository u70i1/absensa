"""Durable publication on POSIX and NTFS; never report failed flushes as success."""

import os


def publish(partial, destination, *, replace=False):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        move.restype = wintypes.BOOL
        # MOVEFILE_WRITE_THROUGH, optionally MOVEFILE_REPLACE_EXISTING.
        if not move(str(partial), str(destination), 8 | int(replace)):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        if replace:
            os.replace(partial, destination)
        else:
            os.link(partial, destination)
            partial.unlink()
        fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
