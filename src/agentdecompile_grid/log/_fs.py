"""Private filesystem helpers shared by the local log and head adapters.

Nothing here is public API.  Three things live here because both ``local.py`` and ``heads.py`` need
them and neither should import the other:

* partition-name validation and the reversible partition -> directory mapping;
* an exclusive advisory file lock that degrades by *name* (``fcntl`` on POSIX, ``msvcrt`` on Windows,
  a ``NotConfigured`` otherwise) instead of silently becoming a no-op;
* atomic replace-write of a small file (temp file in the same directory, fsync, ``os.replace``).
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator, Sequence

from agentdecompile_grid.core import GridError, NotConfigured

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


class InvalidPartition(GridError):
    """A partition name that cannot be a log key: bad characters, ``..``, absolute, too deep."""


_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_PARTITION_DEPTH = 8
MAX_PARTITION_LENGTH = 512


def validate_partition(name: str) -> str:
    """Return ``name`` if it is a legal partition key, else raise ``InvalidPartition`` by name.

    A partition key is one to eight components joined by ``/``; each component starts with an
    alphanumeric and continues with ``[A-Za-z0-9._-]``.  ``..``, ``.``, empty components, leading or
    trailing slashes and backslashes are all rejected, so the key maps to a relative directory path
    reversibly (``/`` <-> ``os.sep``) and can never escape the store root.
    """
    if not isinstance(name, str) or not name:
        raise InvalidPartition("partition name must be a non-empty string")
    if len(name) > MAX_PARTITION_LENGTH:
        raise InvalidPartition(f"partition name longer than {MAX_PARTITION_LENGTH} chars: {name[:40]!r}...")
    parts = name.split("/")
    if len(parts) > MAX_PARTITION_DEPTH:
        raise InvalidPartition(f"partition name deeper than {MAX_PARTITION_DEPTH} components: {name!r}")
    for part in parts:
        if not _COMPONENT.match(part):
            raise InvalidPartition(f"partition component {part!r} in {name!r} is not [A-Za-z0-9][A-Za-z0-9._-]*")
    return name


def partition_components(name: str) -> Sequence[str]:
    return tuple(validate_partition(name).split("/"))


def partition_dir(root: Path, name: str) -> Path:
    """Directory for a partition under ``root``; reversible with ``partition_name``."""
    return root.joinpath(*partition_components(name))


def partition_name(root: Path, directory: Path) -> str:
    """Inverse of ``partition_dir``."""
    rel = directory.resolve().relative_to(root.resolve())
    return validate_partition("/".join(rel.parts))


@contextmanager
def exclusive_lock(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on ``lock_path`` for the block.

    Cross-process and cross-thread (each call opens its own descriptor, so two threads in one process
    contend like two processes do).  Without any locking primitive the adapter refuses by name
    rather than pretending: a CAS that is not atomic is not a CAS.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        elif msvcrt is not None:  # pragma: no cover - Windows
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
        else:  # pragma: no cover
            raise NotConfigured(
                "no file-locking primitive on this platform (needs fcntl or msvcrt); "
                "use a head store with a server-side CAS instead of LocalFileHeads"
            )
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows
                try:
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
    finally:
        os.close(fd)


def write_atomic(path: Path, data: bytes, *, fsync: bool = True) -> None:
    """Replace ``path`` with ``data`` atomically: temp file beside it, fsync, ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        write_all(fd, data)
        if fsync:
            os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    if fsync:
        fsync_dir(path.parent)


def fsync_dir(directory: Path) -> None:
    """Make a rename durable; a no-op where directories cannot be opened (Windows)."""
    try:
        dfd = os.open(str(directory), os.O_RDONLY)
    except OSError:  # pragma: no cover
        return
    try:
        os.fsync(dfd)
    except OSError:  # pragma: no cover
        pass
    finally:
        os.close(dfd)


def write_all(fd: int, data: bytes) -> None:
    """``os.write`` in a loop: a single call may write fewer bytes than asked."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


append_all = write_all
