"""Cross-platform non-blocking file locking (Unix fcntl / Windows msvcrt)."""

from __future__ import annotations

import sys

_IS_WINDOWS = sys.platform == "win32"


def lock_exclusive(fd) -> None:
    """Acquire a non-blocking exclusive lock. Raises BlockingIOError if held."""
    if _IS_WINDOWS:
        import msvcrt
        try:
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise BlockingIOError("File lock held by another process")
    else:
        import fcntl
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock(fd) -> None:
    """Release file lock."""
    if _IS_WINDOWS:
        import msvcrt
        try:
            msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
