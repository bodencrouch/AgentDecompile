"""Read-only wine-prefix clearance probe (ledger P0.3).

wineserver daemonizes and may leave the job's session, so an empty session
does not prove the prefix is idle. This module asks the prefix's wineserver
lock directly and answers ``clear``, ``live`` or ``unknown``.

It never starts Wine, never signals a process, never creates, truncates or
locks a file. Anything outside the layout Wine itself produces is
``unknown``, never ``clear``.

Source relied on (Wine master 4e819f05, 2026-09-25, gitlab.winehq.org):

- ``dlls/ntdll/unix/server.c`` ``init_server_dir`` (~l.1303):
  ``/tmp/.wine-%u/server-%llx-%llx`` from ``getuid()`` and the prefix's
  ``st_dev``/``st_ino`` (non-Android; Android uses ``<prefix>/.wineserver``).
- ``server/request.c`` ``create_server_dir`` (~l.577): the prefix is
  ``chdir``ed and ``fstat``ed (symlinks followed) and must be owned by the uid.
  ``create_dir`` (~l.560) rejects a non-directory, a foreign owner, or
  ``mode & 077`` for both the base and the server dir.
- ``create_server_lock`` (~l.655): ``lock`` must be a regular file.
- ``acquire_lock`` (~l.742): the server holds ``F_WRLCK`` on byte 0, length 1
  for its lifetime. If locks are unsupported (``ENOLCK``) the socket itself
  acts as the lock. ``socket_cleanup`` (~l.552) unlinks only ``socket`` on exit.
- ``kill_lock_owner`` (~l.700): Wine's own non-mutating ``F_GETLK`` probe,
  which this module mirrors without the signal.
"""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import struct
import sys
from pathlib import Path
from typing import Any

SOURCE = ("wine master 4e819f05 (2026-09-25): dlls/ntdll/unix/server.c init_server_dir; "
          "server/request.c create_dir, create_server_dir, create_server_lock, acquire_lock, "
          "socket_cleanup, kill_lock_owner")

# Linux x86_64/aarch64 ``struct flock``: short l_type, short l_whence, off_t
# l_start, off_t l_len, pid_t l_pid, padded to 32 bytes.
_FLOCK = "hhqqi"
_FLOCK_SIZE = 32


def server_dir_for(prefix: str | os.PathLike[str], *, server_root: str | os.PathLike[str] | None = None,
                   uid: int | None = None) -> Path:
    """Return the wineserver directory Wine would use for ``prefix``."""
    st = os.stat(prefix)
    root = Path(server_root) if server_root is not None else Path(f"/tmp/.wine-{os.getuid() if uid is None else uid}")
    return root / f"server-{st.st_dev:x}-{st.st_ino:x}"


def _result(state: str, reason: str, **evidence: Any) -> dict:
    return {"state": state, "evidence": {"reason": reason, "source": SOURCE, **evidence}}


def _check_dir(path: Path, uid: int) -> str | None:
    """Wine's ``create_dir`` rules, via lstat. Return a failure reason or None."""
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode):
        return "not_a_directory"
    if st.st_uid != uid:
        return "foreign_owner"
    if st.st_mode & 0o077:
        return "accessible_by_others"
    return None


def _probe_lock(fd: int) -> tuple[int, int]:
    """F_GETLK for a write lock on byte 0, length 1. Returns (l_type, l_pid)."""
    query = struct.pack(_FLOCK, fcntl.F_WRLCK, os.SEEK_SET, 0, 1, 0).ljust(_FLOCK_SIZE, b"\0")
    reply = fcntl.fcntl(fd, fcntl.F_GETLK, query)
    l_type, _, _, _, l_pid = struct.unpack_from(_FLOCK, reply)
    return l_type, l_pid


def wineprefix_clearance(prefix: str | os.PathLike[str], *, server_root: str | os.PathLike[str] | None = None,
                         uid: int | None = None) -> dict:
    """Return ``{"state": "clear"|"live"|"unknown", "evidence": {...}}`` for ``prefix``.

    ``server_root`` and ``uid`` exist for tests; production callers pass only
    the prefix. The check covers the calling uid's ``/tmp`` view only.
    """
    uid = os.getuid() if uid is None else uid
    if not sys.platform.startswith("linux") or struct.calcsize("P") != 8:
        return _result("unknown", "unsupported_platform", platform=sys.platform)
    prefix_s = os.fspath(prefix)
    if not os.path.isabs(prefix_s):
        return _result("unknown", "prefix_not_absolute", prefix=prefix_s)
    try:
        pst = os.stat(prefix_s)
    except OSError as exc:
        # A deleted prefix can still have a live server on its old inode.
        return _result("unknown", "prefix_stat_failed", prefix=prefix_s, errno=errno.errorcode.get(exc.errno, exc.errno))
    if not stat.S_ISDIR(pst.st_mode) or pst.st_uid != uid:
        return _result("unknown", "prefix_not_owned_directory", prefix=prefix_s)
    root = Path(server_root) if server_root is not None else Path(f"/tmp/.wine-{uid}")
    sdir = root / f"server-{pst.st_dev:x}-{pst.st_ino:x}"
    base = {"prefix": prefix_s, "prefixRealpath": os.path.realpath(prefix_s), "uid": uid,
            "dev": f"{pst.st_dev:x}", "ino": f"{pst.st_ino:x}", "serverDir": str(sdir)}

    for path, missing_reason in ((root, "server_root_absent"), (sdir, "server_dir_absent")):
        try:
            bad = _check_dir(path, uid)
        except FileNotFoundError:
            return _result("clear", missing_reason, **base)
        except OSError as exc:
            return _result("unknown", "stat_failed", path=str(path), errno=errno.errorcode.get(exc.errno, exc.errno), **base)
        if bad:
            return _result("unknown", bad, path=str(path), **base)

    lock, sock = sdir / "lock", sdir / "socket"
    try:
        socket_present = os.path.lexists(sock) if os.access(sdir, os.X_OK) else None
        fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY)
    except FileNotFoundError:
        # create_server_lock follows create_dir immediately; a dir without a
        # lock is a server mid-start or a foreign layout, not a post-exit one.
        return _result("unknown", "lock_absent", socketPresent=socket_present, **base)
    except OSError as exc:
        reason = "lock_not_regular" if exc.errno == errno.ELOOP else "lock_open_failed"
        return _result("unknown", reason, errno=errno.errorcode.get(exc.errno, exc.errno), **base)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return _result("unknown", "lock_not_regular", **base)
        try:
            l_type, l_pid = _probe_lock(fd)
        except OSError as exc:
            return _result("unknown", "lock_probe_failed", errno=errno.errorcode.get(exc.errno, exc.errno), **base)
    finally:
        os.close(fd)

    if l_type != fcntl.F_UNLCK:
        # l_pid is 0 when the holder is in another PID namespace; still live.
        return _result("live", "lock_held", lockHolderPid=l_pid, lockType=l_type, socketPresent=socket_present, **base)
    if socket_present is not False:
        # Crashed server, or the ENOLCK fallback where the socket is the lock.
        return _result("unknown", "socket_without_lock_holder", socketPresent=socket_present, **base)
    return _result("clear", "lock_unheld", socketPresent=False, **base)
