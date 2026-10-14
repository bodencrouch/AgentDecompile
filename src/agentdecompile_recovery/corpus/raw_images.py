"""Resolve the original image bytes of a registered build (register A4).

Every verb that needs a build's raw image goes through
:func:`resolve_raw_image`. It walks a registry of resolvers in a declared
order, stops at the first hit, and materializes that hit at the path
``ghidra_bulk.raw_image_path`` names (``<work_dir>/extract/raw/<slug>``), so
each later verb (``backfill``, ``export-hookpack``) finds the image on disk
without knowing where it came from.

Row context
    A resolver sees one ``binary`` row as a plain ``dict``. The caller may
    add two context keys derived from the store, so resolvers stay free of
    database handles:

    ``program_bindings``
        ``[(locator, program), ...]`` from ``program_binding`` for the row's
        ``repo_path``. A locator is a project file (``.gpr``), a project
        directory, a repository directory, or a ``ghidra:`` URL.
    ``identity_sources``
        ``[(source_path, sha256), ...]`` from ``binary_content_identity`` for
        the row's ``repo_path`` and from ``binary_source_alias`` for the
        row's ``slug``.

    :func:`row_context` builds both from a connection.

Miss reasons
    A resolver reports a reasoned miss by raising :class:`RawImageMiss`;
    the walker turns it into ``None`` and records ``misses[<name>] =
    <reason>``. Returning ``None`` is an unreasoned miss (``"miss"``). Any
    other exception is recorded as ``error:<ExceptionType>`` and the walk
    continues; a resolver never stops the verb.

Names
    Provenance never carries a slug or a path. Where a path or slug must be
    referenced it is written as ``sha256(value)[:12]``.

Hashing streams ``hashlib.sha256`` over 1 MiB chunks. No resolver holds an
image in memory: a resolver that produces bytes (a program's stored file
bytes, from the shared repository or a local project) spools them to a
temporary file while hashing, and the walker moves or copies that file
into place.

Project-backed resolvers
    ``ghidra_store_file_bytes`` first reads an exact bound program directly
    from its on-disk Ghidra item store, without a JVM or server login.
    Analyzer-backed ``ghidra_repository`` and ``ghidra_file_bytes`` remain
    fallbacks for shared server and local project access. All accepted image
    bytes are hashed while spooling and checked against a registered hash
    when available. :func:`describe_resolvers` lists each resolver.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

CHUNK = 1 << 20

#: Environment override for the resolver walk order (comma-separated names).
ORDER_ENV = "AGENT_DECOMPILE_RAW_IMAGE_RESOLVERS"
#: JSON file ``{"<sha256(slug)>": "<path>"}`` read by ``explicit_map``.
MAP_ENV = "AGENT_DECOMPILE_RAW_IMAGE_MAP"
#: ``1`` lets ``ghidra_file_bytes`` reset a project lock's owner. Off by
#: default: a held lock usually means a live analysis session.
RESET_OWNER_ENV = "AGENT_DECOMPILE_GHIDRA_RESET_OWNER"


def sha12(value: str | os.PathLike | None) -> str:
    """``sha256(value)[:12]``: the only form a name or path takes in output."""
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


class RawImageError(ValueError):
    """A refusal: the resolver configuration itself is wrong (unknown name)."""


class RawImageMiss(Exception):
    """A resolver's reasoned miss. ``reason`` is a short machine token."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RawImage:
    """One resolved image.

    ``bytes`` is set only when a resolver produced bytes and chose to keep
    them (none of the built-in resolvers do); ``path`` is the file on disk
    (after the walk: the materialized raw-dir path when materialization was
    allowed). ``sha256`` and ``size`` are always set. ``provenance`` is a
    small sorted dict with no names inside.
    """

    bytes: bytes | None
    path: Path | None
    sha256: str
    size: int
    resolver: str
    provenance: dict = field(default_factory=dict)

    def as_record(self) -> dict:
        """JSON-safe view for receipts: no path values, no bytes."""
        return {
            "path_sha12": sha12(self.path) if self.path is not None else None,
            "provenance": {k: self.provenance[k] for k in sorted(self.provenance)},
            "resolver": self.resolver,
            "sha256": self.sha256,
            "size": int(self.size),
        }


@runtime_checkable
class RawImageResolver(Protocol):
    """One way to find a build's original bytes.

    ``resolve`` returns a :class:`RawImage` whose ``path`` is a readable
    file, or ``None`` / raises :class:`RawImageMiss`. It must respect
    ``deadline_s`` (seconds) and never block past it.
    """

    name: str

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None: ...


# --- hashing -----------------------------------------------------------------


def stream_sha256(path: Path) -> tuple[str, int]:
    """Streamed sha256 and size of *path*; 1 MiB chunks."""
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_copy(src: Path, dst: Path) -> tuple[str, int]:
    """Copy *src* to *dst* through a temp file in ``dst``'s directory.

    Hashes while copying (one pass), fsyncs, renames atomically. Returns
    ``(sha256, size)`` of the bytes written.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    size = 0
    fd, tmp_name = tempfile.mkstemp(prefix=".raw-", suffix=".tmp", dir=str(dst.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            while True:
                chunk = inp.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                size += len(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, dst)
        _fsync_dir(dst.parent)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return h.hexdigest(), size


# --- paths ---------------------------------------------------------------------


def raw_image_target(repo_path: str, work_dir: Path | None) -> Path:
    """Where the image of *repo_path* lives once materialized.

    Mirrors ``ghidra_bulk.raw_image_path``: an explicit raw directory
    (``AGENT_DECOMPILE_EXTRACT_RAW`` or ``ghidra_bulk.EXTRACT_RAW``) wins;
    otherwise ``<work_dir>/extract/raw/<slug-from-repo_path>`` with
    *work_dir* falling back to ``AGENT_DECOMPILE_CORPUS_WORK_DIR`` and then
    the current directory.
    """
    from . import ghidra_bulk

    env_raw = os.environ.get("AGENT_DECOMPILE_EXTRACT_RAW", "").strip()
    if ghidra_bulk.EXTRACT_RAW is not None or env_raw or work_dir is None:
        return Path(ghidra_bulk.raw_image_path(repo_path))
    slug = (repo_path or "").strip("/").replace("/", "__")
    return Path(work_dir) / "extract" / "raw" / slug


def raw_image_root(work_dir: Path | None) -> Path:
    """Directory that :func:`raw_image_target` files land in."""
    return raw_image_target("__probe__", work_dir).parent


def _inside_analysis_project(path: Path) -> bool:
    """True when *path* is a project file or lies inside a project directory."""
    if path.suffix.lower() == ".gpr":
        return True
    return any(part.lower().endswith(".rep") for part in path.parts)


# --- resolvers -----------------------------------------------------------------


class ExtractRawDirResolver:
    """The image is already at :func:`raw_image_target`."""

    name = "extract_raw_dir"
    working = True
    env = ("AGENT_DECOMPILE_EXTRACT_RAW", "AGENT_DECOMPILE_CORPUS_WORK_DIR")
    misses = ("not_materialized",)

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        target = raw_image_target(str(row.get("repo_path") or ""), work_dir)
        if not target.is_file():
            raise RawImageMiss("not_materialized")
        digest, size = stream_sha256(target)
        return RawImage(None, target, digest, size, self.name, {"locator_kind": "raw_dir"})


class RepoPathFileResolver:
    """The row's ``repo_path`` is an existing regular file outside any
    analysis project directory."""

    name = "repo_path_file"
    working = True
    env = ()
    misses = ("repo_path_empty", "repo_path_in_project", "repo_path_is_dir", "repo_path_missing")

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        repo = str(row.get("repo_path") or "")
        if not repo:
            raise RawImageMiss("repo_path_empty")
        path = Path(repo)
        if _inside_analysis_project(path):
            raise RawImageMiss("repo_path_in_project")
        if path.is_dir():
            raise RawImageMiss("repo_path_is_dir")
        if not path.is_file():
            raise RawImageMiss("repo_path_missing")
        digest, size = stream_sha256(path)
        return RawImage(None, path, digest, size, self.name, {"locator_kind": "repo_path"})


class ExplicitMapResolver:
    """A JSON map ``{"<sha256(slug)>": "<path>"}`` at ``AGENT_DECOMPILE_RAW_IMAGE_MAP``.

    Keys are the full hex sha256 of the slug; the 12-character prefix used
    in receipts is accepted too. The map file therefore carries no names.
    """

    name = "explicit_map"
    working = True
    env = (MAP_ENV,)
    misses = ("map_unset", "map_unreadable", "map_not_object", "map_no_entry", "map_path_missing")

    def _load(self) -> dict:
        raw = os.environ.get(MAP_ENV, "").strip()
        if not raw:
            raise RawImageMiss("map_unset")
        try:
            data = json.loads(Path(raw).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RawImageMiss("map_unreadable") from None
        if not isinstance(data, dict):
            raise RawImageMiss("map_not_object")
        return data

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        data = self._load()
        full = hashlib.sha256(str(row.get("slug") or "").encode("utf-8")).hexdigest()
        entry = data.get(full, data.get(full[:12]))
        if not entry:
            raise RawImageMiss("map_no_entry")
        path = Path(str(entry))
        if not path.is_file():
            raise RawImageMiss("map_path_missing")
        digest, size = stream_sha256(path)
        return RawImage(None, path, digest, size, self.name, {"locator_kind": "map"})


class ContentIdentityTableResolver:
    """``binary_content_identity`` / ``binary_source_alias`` rows whose
    ``source_path`` exists on disk (``identity_sources`` row context).

    A source whose current bytes no longer hash to the recorded sha256 is a
    miss (``identity_source_changed``): the table records what the bytes
    were, not what they are now.
    """

    name = "content_identity_table"
    working = True
    env = ()
    misses = ("no_identity_rows", "identity_source_missing", "identity_source_changed")

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        sources = list(row.get("identity_sources") or [])
        if not sources:
            raise RawImageMiss("no_identity_rows")
        reasons: list[str] = []
        for source_path, recorded in sorted(sources):
            path = Path(str(source_path))
            if not path.is_file():
                reasons.append("identity_source_missing")
                continue
            digest, size = stream_sha256(path)
            if recorded and str(recorded).strip().lower() != digest:
                reasons.append("identity_source_changed")
                continue
            return RawImage(None, path, digest, size, self.name, {"locator_kind": "identity_table"})
        raise RawImageMiss(sorted(set(reasons))[0] if reasons else "no_identity_rows")


class _DaemonWorker:
    """One daemon thread running callables in order; results via Futures.

    A ``ThreadPoolExecutor`` joins its threads at interpreter exit, so a
    call that hangs inside the analyzer past its deadline would keep the
    process alive. A daemon thread does not.
    """

    def __init__(self, name: str) -> None:
        import queue

        self._queue: "queue.Queue[tuple[concurrent.futures.Future, object] | None]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            future, fn = item
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn())  # type: ignore[operator]
            except BaseException as exc:  # delivered to the waiter
                future.set_exception(exc)

    def submit(self, fn) -> concurrent.futures.Future:
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._queue.put((future, fn))
        return future


class _AnalyzerWorker:
    """The thread-and-deadline discipline every analyzer-backed resolver shares.

    One lazily started :class:`_DaemonWorker` per resolver (a call that
    hangs in one resolver's thread must not queue the other resolver's
    calls behind it). :meth:`run` submits a callable and waits at most
    ``deadline_s``; the first timeout latches ``unavailable`` to
    *deadline_reason* so the rest of the process pays one miss per row
    instead of the deadline again. :meth:`latch` records a process-wide
    condition (an unreachable server, a missing install) the same way.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._worker: _DaemonWorker | None = None
        self._lock = threading.Lock()
        self.unavailable: str | None = None

    def submit(self, fn) -> concurrent.futures.Future:
        with self._lock:
            if self._worker is None:
                self._worker = _DaemonWorker(self._name)
            return self._worker.submit(fn)

    def latch(self, reason: str) -> None:
        self.unavailable = reason

    def run(self, fn, deadline_s: float, *, deadline_reason: str):
        """``fn()`` on the worker thread, or :class:`RawImageMiss` on timeout."""
        if self.unavailable:
            raise RawImageMiss(self.unavailable)
        future = self.submit(fn)
        try:
            return future.result(timeout=max(0.0, float(deadline_s)))
        except concurrent.futures.TimeoutError:
            self.unavailable = deadline_reason
            raise RawImageMiss(deadline_reason) from None


# --- spooling a program's stored file bytes (worker thread only) ----------------


@dataclass(frozen=True)
class _Spooled:
    """A program's single ``FileBytes`` streamed to a temp file and hashed."""

    path: Path
    sha256: str
    size: int
    filename_sha12: str
    count: int


class _SpoolMiss(Exception):
    """Why :func:`_spool_program` produced nothing. ``kind`` is one of
    ``file_bytes_error``, ``no_file_bytes``, ``ambiguous_file_bytes``,
    ``deadline``, ``file_bytes_short``; each resolver maps it to its own
    miss token. ``count`` is the number of ``FileBytes`` entries seen."""

    def __init__(self, kind: str, count: int = 0):
        super().__init__(kind)
        self.kind = kind
        self.count = count


#: ``ghidra_file_bytes`` miss tokens per spool kind (unchanged from before the
#: extraction; the attestation baseline counts these strings).
_FILE_BYTES_SPOOL_REASONS: dict[str, str] = {
    "file_bytes_error": "ghidra_file_bytes_error",
    "no_file_bytes": "no_file_bytes",
    "ambiguous_file_bytes": "ambiguous_file_bytes",
    "deadline": "ghidra_deadline",
    "file_bytes_short": "ghidra_file_bytes_short",
}

#: ``ghidra_repository`` miss tokens per spool kind.
_REPOSITORY_SPOOL_REASONS: dict[str, str] = {
    "file_bytes_error": "repository_file_bytes_error",
    "no_file_bytes": "no_file_bytes",
    "ambiguous_file_bytes": "ambiguous_file_bytes",
    "deadline": "repository_deadline",
    "file_bytes_short": "repository_file_bytes_short",
}


def _spool_program(program, deadline: float) -> _Spooled:
    """Stream the program's single ``FileBytes`` into a temp file, hashing
    on the way. Raises :class:`_SpoolMiss` otherwise. Exactly one entry is
    required: a guessed concatenation of several would produce a permanent
    wrong hash (R3 never clears a stored value)."""
    try:
        entries = list(program.getMemory().getAllFileBytes())
    except Exception:
        raise _SpoolMiss("file_bytes_error") from None
    if len(entries) != 1:
        raise _SpoolMiss("ambiguous_file_bytes" if entries else "no_file_bytes", len(entries))
    fb = entries[0]
    try:
        import jpype  # type: ignore[import-not-found]

        total = int(fb.getSize())
        buf = jpype.JArray(jpype.JByte)(CHUNK)
    except Exception:
        raise _SpoolMiss("file_bytes_error", 1) from None
    h = hashlib.sha256()
    fd, tmp_name = tempfile.mkstemp(prefix="raw-image-", suffix=".spool")
    tmp = Path(tmp_name)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            offset = 0
            while offset < total:
                if time.monotonic() > deadline:
                    raise TimeoutError
                n = int(fb.getOriginalBytes(offset, buf))
                if n <= 0:
                    break
                chunk = _jbytes(buf, n)
                h.update(chunk)
                out.write(chunk)
                size += n
                offset += n
            out.flush()
            os.fsync(out.fileno())
    except TimeoutError:
        tmp.unlink(missing_ok=True)
        raise _SpoolMiss("deadline", 1) from None
    except Exception:
        tmp.unlink(missing_ok=True)
        raise _SpoolMiss("file_bytes_error", 1) from None
    if size != total:
        tmp.unlink(missing_ok=True)
        raise _SpoolMiss("file_bytes_short", 1)
    try:
        fname = str(fb.getFilename())
    except Exception:
        fname = ""
    return _Spooled(tmp, h.hexdigest(), size, sha12(fname), 1)


# --- lock policies for local analysis projects ----------------------------------


@runtime_checkable
class LockPolicy(Protocol):
    """What ``ghidra_file_bytes`` does when a local project's lock is held.

    ``open`` receives *attempt*, a callable that tries the open once and
    returns ``(project | None, reason | None)`` where a held lock is the
    reason ``ghidra_project_locked``; *deadline* is a ``time.monotonic``
    instant the policy must not run past. It returns the same pair.
    """

    name: str

    def open(self, attempt, deadline: float) -> tuple[object | None, str | None]: ...


class RefuseLockPolicy:
    """Default: one attempt; a held lock is the miss ``ghidra_project_locked``
    (a held lock usually means a live analysis session)."""

    name = "refuse"

    def open(self, attempt, deadline: float) -> tuple[object | None, str | None]:
        return attempt()


class WaitBoundedLockPolicy:
    """Retry the open every ``interval_s`` while the lock is held.

    Bounded by *seconds* (``None``: the row deadline) and always by the row
    deadline less one interval, so the last attempt cannot run the outer
    ``future.result`` wait past its timeout. Still locked at the bound:
    ``ghidra_project_locked``.
    """

    name = "wait"

    def __init__(self, seconds: float | None = None, interval_s: float = 2.0) -> None:
        self.seconds = None if seconds is None else max(0.0, float(seconds))
        self.interval_s = max(0.1, float(interval_s))

    def open(self, attempt, deadline: float) -> tuple[object | None, str | None]:
        stop = float(deadline) - self.interval_s
        if self.seconds is not None:
            stop = min(stop, time.monotonic() + self.seconds)
        project, why = attempt()
        while project is None and why == "ghidra_project_locked":
            remaining = stop - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(self.interval_s, remaining))
            project, why = attempt()
        return project, why


class CopyOnLockPolicy:
    """Slot (A4c): copy the locked project directory into the work
    directory and open the copy with ``resetOwner=True``, leaving the live
    session's lock untouched. A held lock raises ``NotImplementedError``,
    which the walker records as ``not_implemented:A4c``."""

    name = "copy"

    def open(self, attempt, deadline: float) -> tuple[object | None, str | None]:
        project, why = attempt()
        if project is None and why == "ghidra_project_locked":
            raise NotImplementedError("A4c")
        return project, why


#: Selected by ``AGENT_DECOMPILE_PROJECT_LOCK_POLICY`` (``refuse|wait|copy``).
LOCK_POLICY_ENV = "AGENT_DECOMPILE_PROJECT_LOCK_POLICY"
#: Optional bound in seconds for the ``wait`` policy (default: the row deadline).
LOCK_WAIT_ENV = "AGENT_DECOMPILE_PROJECT_LOCK_WAIT_S"

LOCK_POLICIES: dict[str, type] = {
    RefuseLockPolicy.name: RefuseLockPolicy,
    WaitBoundedLockPolicy.name: WaitBoundedLockPolicy,
    CopyOnLockPolicy.name: CopyOnLockPolicy,
}


def lock_policy(name: str | None = None) -> LockPolicy:
    """The configured :class:`LockPolicy`. An unknown name or a bad wait
    bound is a named miss (``project_lock_policy_unknown`` /
    ``project_lock_wait_invalid``), never an exception."""
    chosen = (name if name is not None else os.environ.get(LOCK_POLICY_ENV, "")).strip() or RefuseLockPolicy.name
    factory = LOCK_POLICIES.get(chosen)
    if factory is None:
        raise RawImageMiss("project_lock_policy_unknown")
    if factory is WaitBoundedLockPolicy:
        raw = os.environ.get(LOCK_WAIT_ENV, "").strip()
        if not raw:
            return WaitBoundedLockPolicy()
        try:
            return WaitBoundedLockPolicy(float(raw))
        except ValueError:
            raise RawImageMiss("project_lock_wait_invalid") from None
    return factory()


class GhidraFileBytesResolver:
    """Re-materialize the image from a local analysis project's stored file bytes.

    Candidates: the row's ``repo_path`` when it is a project file or a
    ``local:<dir>:<name>:/<path>`` reference, then each ``program_bindings``
    entry (locator + program path). The project is opened with
    ``resetOwner=False`` so a live session keeps its lock; what happens
    when the lock is held is the configured :class:`LockPolicy` (default
    :class:`RefuseLockPolicy`: the miss ``ghidra_project_locked``). The
    program is opened read-only; nothing is saved. Exactly one
    ``FileBytes`` entry is required -- several is ``ambiguous_file_bytes``.

    All analyzer work runs on one daemon thread (:class:`_AnalyzerWorker`)
    and is waited on with the row deadline. Opened projects are kept until
    :meth:`close` so one project serves every row bound to it. After the
    first timeout the resolver reports ``ghidra_deadline`` for the rest of
    the process. When the analyzer bridge is not importable the miss is
    ``ghidra_unavailable``; when no candidate project exists it is
    ``ghidra_project_missing``.
    """

    name = "ghidra_file_bytes"
    working = True
    env = (RESET_OWNER_ENV, LOCK_POLICY_ENV, LOCK_WAIT_ENV, "GHIDRA_INSTALL_DIR", "JAVA_HOME")
    misses = (
        "ghidra_no_binding",
        "ghidra_locator_remote",
        "ghidra_locator_no_project",
        "ghidra_locator_ambiguous",
        "ghidra_locator_missing",
        "ghidra_locator_invalid",
        "ghidra_unavailable",
        "ghidra_deadline",
        "ghidra_project_missing",
        "ghidra_project_locked",
        "ghidra_project_open_error",
        "ghidra_program_missing",
        "ghidra_file_bytes_error",
        "ghidra_file_bytes_short",
        "no_file_bytes",
        "ambiguous_file_bytes",
        "project_lock_policy_unknown",
        "project_lock_wait_invalid",
    )

    def __init__(self) -> None:
        self._worker = _AnalyzerWorker("raw-image-ghidra")
        self._projects: dict[tuple[str, str], object] = {}

    # -- candidates ---------------------------------------------------------

    @staticmethod
    def _candidates(row: dict) -> tuple[list[tuple[Path, str, str | None]], set[str]]:
        """``[(project_dir, project_name, program_path|None)]`` and skip reasons."""
        out: list[tuple[Path, str, str | None]] = []
        skipped: set[str] = set()
        repo = str(row.get("repo_path") or "")
        if repo.startswith("local:"):
            # The same ``local:<dir>:<name>:/<path>`` form ghidra_env.open_program takes.
            parts = repo.split(":", 3)
            if len(parts) == 4 and parts[1] and parts[2]:
                out.append((Path(parts[1]), parts[2], "/" + parts[3].replace("\\", "/").lstrip("/")))
            else:
                skipped.add("ghidra_locator_invalid")
        elif repo.lower().endswith(".gpr"):
            p = Path(repo)
            out.append((p.parent, p.stem, None))
        for locator, program in sorted((str(a), str(b)) for a, b in (row.get("program_bindings") or [])):
            loc = locator.replace("\\", "/").rstrip("/")
            if "://" in loc or loc.startswith("ghidra:"):
                skipped.add("ghidra_locator_remote")
                continue
            lp = Path(loc)
            prog = "/" + program.replace("\\", "/").lstrip("/") if program else None
            if lp.suffix.lower() == ".gpr":
                out.append((lp.parent, lp.stem, prog))
            elif lp.suffix.lower() == ".rep":
                out.append((lp.parent, lp.stem, prog))
            elif lp.is_dir():
                gprs = sorted(lp.glob("*.gpr"))
                if len(gprs) == 1:
                    out.append((lp, gprs[0].stem, prog))
                elif not gprs:
                    skipped.add("ghidra_locator_no_project")
                else:
                    skipped.add("ghidra_locator_ambiguous")
            else:
                skipped.add("ghidra_locator_missing")
        return out, skipped

    # -- thread -------------------------------------------------------------

    def _submit(self, fn) -> concurrent.futures.Future:
        return self._worker.submit(fn)

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        if self._worker.unavailable:
            raise RawImageMiss(self._worker.unavailable)
        policy = lock_policy()  # a bad policy name is a named miss, raised here
        candidates, skipped = self._candidates(row)
        if not candidates:
            raise RawImageMiss(sorted(skipped)[0] if skipped else "ghidra_no_binding")
        repo = str(row.get("repo_path") or "")
        result = self._worker.run(
            lambda: self._read(candidates, repo, deadline_s, policy), deadline_s, deadline_reason="ghidra_deadline"
        )
        if isinstance(result, RawImageMiss):
            if result.reason == "ghidra_unavailable":
                self._worker.latch(result.reason)
            raise result
        image, provenance = result
        for name in sorted(skipped):
            provenance.setdefault("skipped_locators", []).append(name)
        return RawImage(None, image[0], image[1], image[2], self.name, provenance)

    # -- analyzer side (worker thread only) ---------------------------------

    def _open_project(
        self, project_dir: Path, project_name: str, policy: LockPolicy, deadline: float
    ) -> tuple[object | None, str | None]:
        key = (str(project_dir), project_name)
        project = self._projects.get(key)
        if project is not None:
            return project, None
        from ghidra.base.project import GhidraProject  # type: ignore[import-not-found]
        from ghidra.framework.model import ProjectLocator  # type: ignore[import-not-found]

        try:
            if not ProjectLocator(str(project_dir), project_name).exists():
                return None, "ghidra_project_missing"
        except Exception:
            return None, "ghidra_project_missing"

        def attempt() -> tuple[object | None, str | None]:
            try:
                if os.environ.get(RESET_OWNER_ENV, "").strip() == "1":
                    from ghidra.pyghidra import PyGhidraProjectManager  # type: ignore[import-not-found]

                    opened = PyGhidraProjectManager().openProject(
                        ProjectLocator(str(project_dir), project_name), False, True
                    )
                    return _GhidraProjectShim(opened), None
                return GhidraProject.openProject(str(project_dir), project_name, False), None
            except Exception as exc:  # LockException / NotOwnerException / IOException
                text = type(exc).__name__ + ":" + str(exc)
                if "Lock" in text or "Owner" in text or "lock" in str(exc).lower():
                    return None, "ghidra_project_locked"
                return None, "ghidra_project_open_error"

        project, why = policy.open(attempt, deadline)
        if project is None:
            return None, why or "ghidra_project_open_error"
        self._projects[key] = project
        return project, None

    def _read(self, candidates, repo: str, deadline_s: float, policy: LockPolicy):
        deadline = time.monotonic() + float(deadline_s)
        try:
            import pyghidra  # type: ignore[import-not-found]
        except ImportError:
            return RawImageMiss("ghidra_unavailable")
        try:
            # One JVM boot path for the whole package: ghidra_env.start owns
            # the install dir, JAVA_HOME_OVERRIDE and the container-support
            # options; a bare pyghidra.start() misses all three.
            from .ghidra_env import start as ghidra_start

            if not pyghidra.started() and not ghidra_start():
                return RawImageMiss("ghidra_unavailable")
        except Exception:
            return RawImageMiss("ghidra_unavailable")
        reasons: list[str] = []
        basename = Path(repo).name.casefold()
        for project_dir, project_name, program_path in candidates:
            if time.monotonic() > deadline:
                return RawImageMiss("ghidra_deadline")
            project, why = self._open_project(project_dir, project_name, policy, deadline)
            if project is None:
                reasons.append(why or "ghidra_project_missing")
                continue
            programs = [program_path] if program_path else self._programs_named(project, basename)
            if not programs:
                reasons.append("ghidra_program_missing")
                continue
            for ppath in programs:
                folder, _, pname = ppath.rpartition("/")
                folder = folder or "/"
                try:
                    program = project.openProgram(folder, pname, True)
                except Exception:
                    reasons.append("ghidra_program_missing")
                    continue
                try:
                    spooled = _spool_program(program, deadline)
                except _SpoolMiss as miss:
                    reasons.append(_FILE_BYTES_SPOOL_REASONS[miss.kind])
                    continue
                finally:
                    try:
                        project.close(program)
                    except Exception:
                        pass
                provenance = {
                    "locator_kind": "ghidra_project",
                    "project_sha12": sha12(str(project_dir / project_name)),
                    "program_sha12": sha12(ppath),
                    "file_bytes_name_sha12": spooled.filename_sha12,
                    "spooled": True,
                }
                return (spooled.path, spooled.sha256, spooled.size), provenance
        return RawImageMiss(sorted(set(reasons))[0] if reasons else "ghidra_project_missing")

    @staticmethod
    def _programs_named(project, basename: str) -> list[str]:
        """Project paths of programs whose name matches *basename* (case-folded)."""
        try:
            from ghidra.framework.model import ProjectDataUtils  # type: ignore[import-not-found]

            root = project.getRootFolder()
            found = []
            for df in ProjectDataUtils.descendantFiles(root):
                name = str(df.getName())
                if name.casefold() == basename or name.casefold().endswith(basename):
                    found.append(str(df.getPathname()))
            return sorted(found)
        except Exception:
            return []

    def close(self) -> dict:
        """Close every project this resolver opened. Returns counts."""
        closed = 0
        errors = 0

        def _close_all():
            nonlocal closed, errors
            for key in sorted(self._projects):
                try:
                    self._projects[key].close()
                    closed += 1
                except Exception:
                    errors += 1
            self._projects.clear()

        if self._projects:
            try:
                self._submit(_close_all).result(timeout=60)
            except concurrent.futures.TimeoutError:
                errors += len(self._projects)
        return {"closed": closed, "errors": errors}


# --- the shared repository -------------------------------------------------------


@runtime_checkable
class RepositoryAccess(Protocol):
    """One way to reach the program a ``repo_path`` names.

    ``unconfigured`` runs on the caller's thread before any analyzer work
    and returns a miss reason when this access cannot be used at all (so
    an unconfigured install never boots the JVM), else ``None``. ``open``
    returns a context manager yielding the program read-only, or ``None``
    when the path is missing; it runs on the worker thread.
    """

    name: str

    def unconfigured(self) -> str | None: ...

    def open(self, repo_path: str): ...


class ServerRepositoryAccess:
    """The shared analysis server's repository, through ``ghidra_env.open_program``
    (host, port, repository, username and key from
    ``corpus_config.load_ghidra_server``: environment first, then
    ``ghidra_server.json`` under ``AGENT_DECOMPILE_CORPUS_CONFIG_DIR``)."""

    name = "server"

    def unconfigured(self) -> str | None:
        from .ghidra_env import server_configured

        return None if server_configured() else "repository_unconfigured"

    def open(self, repo_path: str):
        from .ghidra_env import open_program

        return open_program(repo_path)


class LocalProjectAccess:
    """A ``local:<dir>:<name>:/<path>`` reference, through
    ``ghidra_env.open_local_program``. Chosen automatically for such paths."""

    name = "local"

    def unconfigured(self) -> str | None:
        return None

    def open(self, repo_path: str):
        from .ghidra_env import open_local_program

        return open_local_program(repo_path)


class SnapshotRepositoryAccess:
    """Slot (A4c): a checked-out copy of the repository directory, for the
    locked and offline cases. Contract: open the program from the snapshot's
    own project data without contacting the server."""

    name = "snapshot"

    def unconfigured(self) -> str | None:
        raise NotImplementedError("A4c")

    def open(self, repo_path: str):
        raise NotImplementedError("A4c")


#: Selects the access for non-``local:`` paths (``server|snapshot``).
REPOSITORY_ACCESS_ENV = "AGENT_DECOMPILE_REPOSITORY_ACCESS"

REPOSITORY_ACCESS: dict[str, RepositoryAccess] = {
    a.name: a for a in (ServerRepositoryAccess(), LocalProjectAccess(), SnapshotRepositoryAccess())
}


def repository_access(repo_path: str) -> RepositoryAccess:
    """The access for *repo_path*: ``local`` for ``local:`` references, else
    the one ``AGENT_DECOMPILE_REPOSITORY_ACCESS`` names (default ``server``).
    An unknown name is the miss ``repository_access_unknown``."""
    if repo_path.startswith("local:"):
        return REPOSITORY_ACCESS[LocalProjectAccess.name]
    chosen = os.environ.get(REPOSITORY_ACCESS_ENV, "").strip() or ServerRepositoryAccess.name
    access = REPOSITORY_ACCESS.get(chosen)
    if access is None or chosen == LocalProjectAccess.name:
        raise RawImageMiss("repository_access_unknown")
    return access


_AUTH_NAMES = frozenset(
    {
        "UserAccessException",
        "LoginException",
        "FailedLoginException",
        "AuthenticationException",
        "KeyStoreException",
        "UnrecoverableKeyException",
        "GeneralSecurityException",
        "SignatureException",
    }
)
_UNREACHABLE_NAMES = frozenset(
    {
        "ConnectException",
        "ConnectIOException",
        "SocketTimeoutException",
        "SocketException",
        "UnknownHostException",
        "NoRouteToHostException",
        "NotConnectedException",
        "RemoteException",
        "ServerException",
        "UnmarshalException",
        "ServerNotActiveException",
    }
)
_VERSION_NAMES = frozenset({"VersionException", "VersionMismatchException", "UnsupportedClassVersionError"})
_AUTH_WORDS = ("keystore", "authenticat", "password", "unauthorized", "not authorized", "access denied", "permission denied", "credential", "login")
_VERSION_WORDS = ("version",)
_UNREACHABLE_WORDS = ("connection refused", "connect", "timed out", "timeout", "unreachable", "no route", "unknown host", "unavailable", "socket")
_NOT_FOUND_WORDS = ("not found", "does not exist", "no such repository")


def _classify_repository_error(exc: BaseException) -> str:
    """The miss token for an exception raised while reaching the repository.

    Java exceptions reach Python under their simple class name (the whole
    MRO is inspected). The message is inspected for a few keywords and is
    never part of the token: ``ghidra_env.domain_file`` raises a Python
    ``FileNotFoundError`` whose message *is* the program path, and a
    keystore failure names the key file.
    """
    if isinstance(exc, FileNotFoundError):
        return "repository_program_missing"
    names = {c.__name__ for c in type(exc).__mro__}
    try:
        text = str(exc).lower()
    except Exception:
        text = ""
    if names & _AUTH_NAMES:
        return "repository_auth_failed"
    if "FileNotFoundException" in names:
        # The only file the server client opens on this path is the keystore.
        return "repository_auth_failed"
    if names & _UNREACHABLE_NAMES:
        return "repository_unreachable"
    if names & _VERSION_NAMES:
        return "repository_version_conflict"
    if any(w in text for w in _AUTH_WORDS):
        return "repository_auth_failed"
    if any(w in text for w in _NOT_FOUND_WORDS):
        return "repository_not_found"
    if any(w in text for w in _UNREACHABLE_WORDS):
        return "repository_unreachable"
    if "lock" in text:
        return "repository_locked"
    # The widest net last: "version" appears in many unrelated messages.
    if any(w in text for w in _VERSION_WORDS):
        return "repository_version_conflict"
    return "repository_error:" + type(exc).__name__


#: Conditions that hold for every row of one access: once seen, every later
#: row through the same access gets the same miss without another attempt.
#: A local-project failure never latches the server path, and the reverse.
_REPOSITORY_LATCHED = frozenset({"repository_unreachable", "repository_auth_failed", "repository_not_found"})


class GhidraStoreFileBytesResolver:
    """Read original bytes from a bound local project or shared store on disk.

    Unlike the analyzer-backed resolvers, this path needs no Ghidra JVM,
    server login, checkout, or project lock mutation. It opens only the exact
    bound program path and only its original ``File Bytes`` buffers.
    """

    name = "ghidra_store_file_bytes"
    working = True
    env = ()
    misses = (
        "store_no_binding",
        "store_locator_remote",
        "store_locator_missing",
        "store_program_missing",
        "store_program_ambiguous",
        "store_project_error",
        "store_no_file_bytes",
        "store_ambiguous_file_bytes",
        "store_file_bytes_error",
        "store_file_bytes_short",
        "store_file_bytes_hash_mismatch",
        "store_deadline",
    )

    def __init__(self) -> None:
        self._index_lock = threading.RLock()
        self._worker = _AnalyzerWorker("raw-image-store")
        self._roots_by_locator: dict[
            str, tuple[tuple[object, ...], tuple[Path, ...]]
        ] = {}
        self._entries_by_root: dict[
            str, tuple[tuple[object, ...], tuple[object, ...]]
        ] = {}

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size, stat.st_ino

    @classmethod
    def _roots_stamp(cls, locator: Path, roots: tuple[Path, ...]) -> tuple[object, ...]:
        return (
            cls._stamp(locator),
            tuple((str(root), cls._stamp(root)) for root in roots),
        )

    @classmethod
    def _entries_stamp(
        cls, root: Path, index_path: Path, entries: tuple[object, ...]
    ) -> tuple[object, ...]:
        # The project index is the primary membership signal. These additional
        # stamps catch a new Ghidra database version or changed item metadata
        # even when an existing ~index.dat was not rewritten.
        per_entry = tuple(
            (
                cls._stamp(entry.property_file),
                cls._stamp(entry.database_dir),
                cls._stamp(entry.database_path),
            )
            for entry in entries
        )
        return cls._stamp(root), cls._stamp(index_path), per_entry

    @staticmethod
    def _candidates(row: dict) -> tuple[list[tuple[Path, str, str]], set[str]]:
        candidates: list[tuple[Path, str, str]] = []
        skipped: set[str] = set()
        for locator, program in sorted(
            (str(a), str(b)) for a, b in (row.get("program_bindings") or [])
        ):
            normalized = locator.replace("\\", "/").rstrip("/")
            program_path = "/" + program.replace("\\", "/").strip("/")
            if "://" in normalized or normalized.startswith("ghidra:"):
                skipped.add("store_locator_remote")
                continue
            if normalized.startswith("local:"):
                parts = normalized.split(":", 3)
                if len(parts) != 4 or not parts[1] or not parts[2]:
                    skipped.add("store_locator_missing")
                    continue
                project = Path(parts[1]).expanduser() / f"{parts[2]}.rep"
                candidates.append((project, program_path, sha12(locator)))
                continue
            path = Path(normalized).expanduser()
            if not path.exists():
                skipped.add("store_locator_missing")
                continue
            candidates.append((path, program_path, sha12(locator)))
        return candidates, skipped

    @staticmethod
    def _discard_late_spool(future: concurrent.futures.Future) -> None:
        """Remove a spool produced after the caller's deadline has expired."""
        try:
            image = future.result()
        except BaseException:
            return
        if (
            isinstance(image, RawImage)
            and image.resolver == "ghidra_store_file_bytes"
            and image.provenance.get("spooled") is True
            and image.path is not None
        ):
            try:
                image.path.unlink(missing_ok=True)
            except OSError:
                pass

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        if self._worker.unavailable:
            raise RawImageMiss(self._worker.unavailable)
        deadline = time.monotonic() + max(0.0, float(deadline_s))
        future = self._worker.submit(
            lambda: self._resolve_on_worker(row, deadline=deadline)
        )
        try:
            return future.result(timeout=max(0.0, deadline - time.monotonic()))
        except concurrent.futures.TimeoutError:
            self._worker.latch("store_deadline")
            future.add_done_callback(self._discard_late_spool)
            raise RawImageMiss("store_deadline") from None

    def _resolve_on_worker(self, row: dict, *, deadline: float) -> RawImage:
        from ..ghidra_db import list_programs, store_roots

        candidates, skipped = self._candidates(row)
        if not candidates:
            raise RawImageMiss(sorted(skipped)[0] if skipped else "store_no_binding")

        expected = str(row.get("content_sha256") or "").strip().lower()
        reasons: set[str] = set(skipped)
        for locator, program_path, locator_sha in candidates:
            if time.monotonic() >= deadline:
                raise RawImageMiss("store_deadline")
            try:
                locator_key = str(Path(locator).expanduser().resolve())
                with self._index_lock:
                    locator_path = Path(locator_key)
                    roots_cached = self._roots_by_locator.get(locator_key)
                    if roots_cached is None or roots_cached[0] != self._roots_stamp(
                        locator_path, roots_cached[1]
                    ):
                        roots = tuple(store_roots(locator))
                        if roots:
                            root_stamp = self._roots_stamp(locator_path, roots)
                            self._roots_by_locator[locator_key] = (root_stamp, roots)
                        else:
                            self._roots_by_locator.pop(locator_key, None)
                    else:
                        roots = roots_cached[1]
                    exact = []
                    for root in roots:
                        if time.monotonic() >= deadline:
                            raise RawImageMiss("store_deadline")
                        root_key = str(root.resolve())
                        index_path = root / "~index.dat"
                        entries_cached = self._entries_by_root.get(root_key)
                        if entries_cached is None or entries_cached[0] != self._entries_stamp(
                            root, index_path, entries_cached[1]
                        ):
                            entries = tuple(list_programs(root))
                            if entries:
                                entry_stamp = self._entries_stamp(root, index_path, entries)
                                self._entries_by_root[root_key] = (entry_stamp, entries)
                            else:
                                self._entries_by_root.pop(root_key, None)
                        else:
                            entries = entries_cached[1]
                        if time.monotonic() >= deadline:
                            raise RawImageMiss("store_deadline")
                        exact.extend(
                            entry for entry in entries if entry.project_path == program_path
                        )
            except RawImageMiss:
                raise
            except Exception:
                reasons.add("store_project_error")
                continue
            if not exact:
                reasons.add("store_program_missing")
                continue
            if len(exact) != 1:
                reasons.add("store_program_ambiguous")
                continue
            program = None
            try:
                program = exact[0].open()
                sources = program.file_bytes_sources()
                if not sources:
                    reasons.add("store_no_file_bytes")
                    continue
                if len(sources) != 1:
                    reasons.add("store_ambiguous_file_bytes")
                    continue
                source = sources[0]
                if source.size > 512 * 1024 * 1024:
                    reasons.add("store_file_bytes_error")
                    continue
                fd, tmp_name = tempfile.mkstemp(prefix="raw-image-store-", suffix=".spool")
                tmp = Path(tmp_name)
                digest = hashlib.sha256()
                size = 0
                try:
                    with os.fdopen(fd, "wb") as out:
                        for chunk in program.iter_original_file_chunks(source.source_id):
                            if time.monotonic() >= deadline:
                                raise TimeoutError
                            digest.update(chunk)
                            out.write(chunk)
                            size += len(chunk)
                        out.flush()
                        os.fsync(out.fileno())
                    if size != source.size:
                        reasons.add("store_file_bytes_short")
                        tmp.unlink(missing_ok=True)
                        continue
                    sha256 = digest.hexdigest()
                    if expected and sha256 != expected:
                        reasons.add("store_file_bytes_hash_mismatch")
                        tmp.unlink(missing_ok=True)
                        continue
                except TimeoutError:
                    tmp.unlink(missing_ok=True)
                    raise RawImageMiss("store_deadline") from None
                except Exception:
                    tmp.unlink(missing_ok=True)
                    reasons.add("store_file_bytes_error")
                    continue
                return RawImage(
                    None,
                    tmp,
                    sha256,
                    size,
                    self.name,
                    {
                        "locator_sha12": locator_sha,
                        "program_sha12": sha12(program_path),
                        "file_bytes_name_sha12": sha12(source.filename),
                        "file_bytes_source_id": source.source_id,
                        "spooled": True,
                    },
                )
            except RawImageMiss:
                raise
            except Exception:
                reasons.add("store_file_bytes_error")
            finally:
                if program is not None:
                    try:
                        program.close()
                    except Exception:
                        pass
        raise RawImageMiss(sorted(reasons)[0] if reasons else "store_program_missing")


class GhidraRepositoryResolver:
    """Re-materialize the image from the program the corpus's own address names.

    ``binary.repo_path`` is a path inside the shared analysis-server
    repository -- the address every other verb opens through
    ``ghidra_env.open_program``. This resolver opens exactly that program
    read-only (an immutable domain object; nothing is checked out or
    saved) through a :class:`RepositoryAccess` and streams its single
    ``FileBytes`` to a spool.

    Before any analyzer work the access is asked whether it is configured
    at all: with no repository declared the miss is
    ``repository_unconfigured`` and the JVM is never booted. Every failure
    on the worker side is classified into a named miss
    (:func:`_classify_repository_error`). A missing install and a deadline
    latch for the whole resolver; an unreachable server, failed
    authentication or a missing repository latch per access, so a local
    reference's failure never speaks for the server. The one non-miss exit
    is a selected slot (``snapshot`` access), which raises
    ``NotImplementedError("A4c")`` for the walker to record.
    """

    name = "ghidra_repository"
    working = True
    env = (
        REPOSITORY_ACCESS_ENV,
        "AGENT_DECOMPILE_CORPUS_CONFIG_DIR",
        "GHIDRA_SERVER_HOST",
        "GHIDRA_SERVER_PORT",
        "GHIDRA_SERVER_REPOSITORY",
        "GHIDRA_SERVER_USERNAME",
        "GHIDRA_SERVER_SSH_KEY",
        "GHIDRA_INSTALL_DIR",
        "JAVA_HOME",
    )
    misses = (
        "repo_path_empty",
        "repository_path_is_project",
        "repository_access_unknown",
        "repository_unconfigured",
        "repository_analyzer_unavailable",
        "repository_program_missing",
        "repository_auth_failed",
        "repository_unreachable",
        "repository_not_found",
        "repository_version_conflict",
        "repository_locked",
        "repository_deadline",
        "repository_error:<ExceptionClass>",
        "repository_file_bytes_error",
        "repository_file_bytes_short",
        "no_file_bytes",
        "ambiguous_file_bytes",
    )

    def __init__(self) -> None:
        self._worker = _AnalyzerWorker("raw-image-repository")
        self._latched: dict[str, str] = {}  # access name -> miss reason

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        if self._worker.unavailable:
            raise RawImageMiss(self._worker.unavailable)
        repo = str(row.get("repo_path") or "")
        if not repo:
            raise RawImageMiss("repo_path_empty")
        if not repo.startswith("local:") and _inside_analysis_project(Path(repo)):
            # A local project file is ghidra_file_bytes' business; no server round trip.
            raise RawImageMiss("repository_path_is_project")
        access = repository_access(repo)
        reason = access.unconfigured()  # runs here, before the worker: no JVM yet
        if reason:
            raise RawImageMiss(reason)
        if access.name in self._latched:
            raise RawImageMiss(self._latched[access.name])
        outcome = self._worker.run(
            lambda: self._fetch(access, repo, deadline_s), deadline_s, deadline_reason="repository_deadline"
        )
        if isinstance(outcome, RawImageMiss):
            if outcome.reason == "repository_analyzer_unavailable":
                self._worker.latch(outcome.reason)
            elif outcome.reason in _REPOSITORY_LATCHED:
                self._latched[access.name] = outcome.reason
            raise outcome
        spooled: _Spooled = outcome
        provenance = {
            "resolver": self.name,
            "access": access.name,
            "locator_kind": "repository_path",
            "program_ref": sha12(repo),
            "file_bytes_count": int(spooled.count),
            "file_bytes_name_sha12": spooled.filename_sha12,
            "spooled": True,
        }
        return RawImage(None, spooled.path, spooled.sha256, spooled.size, self.name, provenance)

    # -- analyzer side (worker thread only) ---------------------------------

    @staticmethod
    def _fetch(access: RepositoryAccess, repo: str, deadline_s: float):
        """Open the program through *access*, spool it; a :class:`RawImageMiss`
        value (never raised) for every failure except a selected slot."""
        deadline = time.monotonic() + float(deadline_s)
        try:
            from .ghidra_env import start as ghidra_start

            if not ghidra_start():
                return RawImageMiss("repository_analyzer_unavailable")
        except Exception as exc:
            # The boot installs the server authenticator; a missing or
            # unreadable key surfaces here and is an auth failure.
            token = _classify_repository_error(exc)
            return RawImageMiss(token if token == "repository_auth_failed" else "repository_analyzer_unavailable")
        try:
            with access.open(repo) as program:
                if program is None:
                    return RawImageMiss("repository_program_missing")
                return _spool_program(program, deadline)
        except _SpoolMiss as miss:
            return RawImageMiss(_REPOSITORY_SPOOL_REASONS[miss.kind])
        except NotImplementedError:
            raise
        except Exception as exc:
            return RawImageMiss(_classify_repository_error(exc))


class _GhidraProjectShim:
    """Give a raw ``Project`` the two ``GhidraProject`` methods the reader uses."""

    def __init__(self, project):
        self._project = project
        self._consumers: dict = {}

    def getRootFolder(self):
        return self._project.getProjectData().getRootFolder()

    def openProgram(self, folder: str, name: str, read_only: bool):
        from ghidra.framework.model import DomainFile  # type: ignore[import-not-found]
        from ghidra.util.task import TaskMonitor  # type: ignore[import-not-found]
        from java.lang import Object  # type: ignore[import-not-found]

        df = self._project.getProjectData().getFolder(folder).getFile(name)
        if df is None:
            raise FileNotFoundError(name)
        consumer = Object()
        program = df.getReadOnlyDomainObject(consumer, DomainFile.DEFAULT_VERSION, TaskMonitor.DUMMY)
        self._consumers[id(program)] = consumer
        return program

    def close(self, program=None):
        if program is not None:
            consumer = self._consumers.pop(id(program), None)
            if consumer is not None:
                program.release(consumer)
            return
        self._project.close()


def _jbytes(buf, n: int) -> bytes:
    """First *n* bytes of a Java ``byte[]`` as Python bytes."""
    try:
        return bytes(memoryview(buf)[:n])
    except (TypeError, ValueError):
        pass
    try:
        return bytes(buf)[:n]
    except (TypeError, ValueError):
        return bytes((int(buf[i]) & 0xFF) for i in range(n))


# --- named slots ----------------------------------------------------------------


class ObjectStoreResolver:
    """Slot: a content-addressed object store keyed by sha256.

    Contract: when a store locator is configured (the grid's
    ``agentdecompile_grid.objects`` adapters -- local directory, bucket,
    static mirror), fetch the object whose ref is the row's stored
    ``content_sha256`` and return it as a path. A row without a stored
    hash is a miss ``no_stored_hash``; an absent object is ``object_missing``.
    """

    name = "object_store"
    working = False
    env = ()
    misses = ("no_stored_hash", "object_missing")

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        raise NotImplementedError("A4.object_store")


class PeerFetchResolver:
    """Slot: fetch the image from a peer node by content hash.

    Contract: outbound-only HTTP to a configured peer list, verifying the
    returned bytes against the requested sha256 before returning a path.
    Never trusts a peer's claimed hash.
    """

    name = "peer_fetch"
    working = False
    env = ()
    misses = ("no_stored_hash", "peer_unreachable", "peer_hash_mismatch")

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        raise NotImplementedError("A4.peer_fetch")


class ArchiveMemberResolver:
    """Slot: an image inside a corpus ZIP, located through ``archive.py``.

    Contract: given an archive path from configuration and the row's
    ``repo_path`` as the member name, extract that member to a temp file
    (streamed) and return its path; ``member_missing`` otherwise.
    """

    name = "archive_member"
    working = False
    env = ()
    misses = ("archive_unset", "member_missing")

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        raise NotImplementedError("A4.archive_member")


# --- registry -------------------------------------------------------------------

RAW_IMAGE_RESOLVERS: dict[str, RawImageResolver] = {
    r.name: r
    for r in (
        ExtractRawDirResolver(),
        RepoPathFileResolver(),
        ExplicitMapResolver(),
        ContentIdentityTableResolver(),
        GhidraStoreFileBytesResolver(),
        GhidraRepositoryResolver(),
        GhidraFileBytesResolver(),
        ObjectStoreResolver(),
        PeerFetchResolver(),
        ArchiveMemberResolver(),
    )
}

#: Working resolvers, cheapest first. Slots are registered but not walked.
#: The shared repository is the corpus's own program address, so it comes
#: before the local-project fallback.
DEFAULT_RESOLVER_ORDER: tuple[str, ...] = (
    "extract_raw_dir",
    "repo_path_file",
    "explicit_map",
    "content_identity_table",
    "ghidra_store_file_bytes",
    "ghidra_repository",
    "ghidra_file_bytes",
)


def resolver_order(explicit: tuple[str, ...] | list[str] | None = None) -> tuple[str, ...]:
    """The walk order: *explicit*, else ``AGENT_DECOMPILE_RAW_IMAGE_RESOLVERS``,
    else :data:`DEFAULT_RESOLVER_ORDER`. Unknown names raise :class:`RawImageError`."""
    if explicit is None:
        env = os.environ.get(ORDER_ENV, "").strip()
        names = tuple(n.strip() for n in env.split(",") if n.strip()) if env else DEFAULT_RESOLVER_ORDER
    else:
        names = tuple(str(n).strip() for n in explicit if str(n).strip())
    unknown = [n for n in names if n not in RAW_IMAGE_RESOLVERS]
    if unknown:
        raise RawImageError(
            f"unknown raw image resolver: {', '.join(unknown)} (known: {', '.join(sorted(RAW_IMAGE_RESOLVERS))})"
        )
    if not names:
        raise RawImageError("raw image resolver order is empty")
    return names


def row_context(con, row: dict) -> dict:
    """*row* plus ``program_bindings`` and ``identity_sources`` from *con*."""
    out = dict(row)
    repo = str(row.get("repo_path") or "")
    slug = str(row.get("slug") or "")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    bindings: list[tuple[str, str]] = []
    if "program_binding" in tables and repo:
        bindings = sorted(
            (str(a), str(b))
            for a, b in con.execute(
                "SELECT locator, program FROM program_binding WHERE source_path=?", (repo,)
            ).fetchall()
        )
    sources: list[tuple[str, str]] = []
    if "binary_content_identity" in tables and repo:
        sources.extend(
            (str(a), str(b))
            for a, b in con.execute(
                "SELECT source_path, sha256 FROM binary_content_identity WHERE source_path=?", (repo,)
            ).fetchall()
        )
    if "binary_source_alias" in tables and slug:
        sources.extend(
            (str(a), str(b))
            for a, b in con.execute(
                "SELECT source_path, sha256 FROM binary_source_alias WHERE binary_slug=?", (slug,)
            ).fetchall()
        )
    out["program_bindings"] = bindings
    out["identity_sources"] = sorted(set(sources))
    return out


def resolve_raw_image(
    row: dict,
    *,
    order: tuple[str, ...] | None = None,
    work_dir: Path | None = None,
    deadline_s: float = 120.0,
    materialize: bool = True,
    expected_sha256: str | None = None,
) -> RawImage | None:
    """Walk *order* and return the first hit, materialized when allowed.

    ``provenance["misses"]`` records every resolver tried before the hit
    (or all of them on a miss -- then ``None`` is returned and the reasons
    are available through :func:`last_misses`). The per-call deadline is
    shared by the whole walk: each resolver gets what is left.

    A hit whose file is not already at :func:`raw_image_target` is copied
    there (temp file, fsync, atomic rename) and ``provenance["materialized"]``
    is ``True``; a file already there is ``already_present``; a target that
    exists with different bytes is left alone (``materialize_conflict``).
    With ``expected_sha256`` set, a hit whose hash differs is returned but
    never materialized (``contested``), so a disputed image cannot displace
    the stored key's bytes. ``materialize=False`` (dry runs) writes nothing.
    """
    names = resolver_order(order)
    misses: dict[str, str] = {}
    started = time.monotonic()
    hit: RawImage | None = None
    for name in names:
        remaining = float(deadline_s) - (time.monotonic() - started)
        if remaining <= 0:
            misses[name] = "deadline"
            continue
        resolver = RAW_IMAGE_RESOLVERS[name]
        try:
            found = resolver.resolve(row, work_dir=work_dir, deadline_s=remaining)
        except RawImageMiss as miss:
            misses[name] = miss.reason
            continue
        except NotImplementedError as exc:
            misses[name] = f"not_implemented:{exc}"
            continue
        except Exception as exc:  # a resolver never stops the verb
            misses[name] = f"error:{type(exc).__name__}"
            continue
        if found is None:
            misses[name] = "miss"
            continue
        hit = found
        break
    _LAST_MISSES[threading.get_ident()] = dict(misses)
    if hit is None:
        return None

    provenance = dict(hit.provenance)
    provenance["misses"] = {k: misses[k] for k in sorted(misses)}
    provenance["repo_path_sha12"] = sha12(str(row.get("repo_path") or ""))
    provenance["materialized"] = False
    spooled = bool(provenance.pop("spooled", False))
    path = hit.path
    target = raw_image_target(str(row.get("repo_path") or ""), work_dir)
    contested = bool(expected_sha256) and str(expected_sha256).strip().lower() != hit.sha256
    if contested:
        provenance["materialize_skipped"] = "contested"
    elif not materialize:
        provenance["materialize_skipped"] = "disabled"
    elif path is not None and path.resolve() == target.resolve():
        provenance["materialize_skipped"] = "already_present"
    elif target.is_file():
        existing, _ = stream_sha256(target)
        provenance["materialize_skipped"] = "already_present" if existing == hit.sha256 else "materialize_conflict"
        if existing == hit.sha256:
            path = target
    elif path is not None:
        try:
            if spooled:
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.replace(path, target)
                    _fsync_dir(target.parent)
                    written = hit.sha256
                except OSError:
                    written, _ = atomic_copy(path, target)
            else:
                written, _ = atomic_copy(path, target)
            if written != hit.sha256:
                # The source changed under us; the copy is not the image we hashed.
                target.unlink(missing_ok=True)
                provenance["materialize_skipped"] = "source_changed"
            else:
                provenance["materialized"] = True
                path = target
        except OSError as exc:
            provenance["materialize_skipped"] = f"error:{type(exc).__name__}"
    if spooled and hit.path is not None:
        # A spool is transient. Moved into place: the unlink is a no-op.
        # Copied or not materialized: delete it; the hit then keeps its
        # hash and size only.
        try:
            hit.path.unlink(missing_ok=True)
        except OSError:
            pass
        if path == hit.path:
            path = None
    return RawImage(hit.bytes, path, hit.sha256, hit.size, hit.resolver, {k: provenance[k] for k in sorted(provenance)})


_LAST_MISSES: dict[int, dict[str, str]] = {}


def last_misses() -> dict[str, str]:
    """Miss reasons of the most recent :func:`resolve_raw_image` on this thread."""
    return dict(_LAST_MISSES.get(threading.get_ident(), {}))


#: Miss tokens the walker itself records, outside any resolver's vocabulary.
WALKER_MISSES: tuple[str, ...] = ("miss", "deadline", "error:<ExceptionClass>", "not_implemented:<slot>")


def describe_resolvers() -> dict:
    """Every registered resolver: working or slot, its position in the
    default order, its miss vocabulary and the environment variables it
    reads; plus the lock policies, the repository accesses and the
    walker-level knobs. Sorted, JSON-safe, no paths or values inside."""
    resolvers: dict[str, dict] = {}
    for name, resolver in sorted(RAW_IMAGE_RESOLVERS.items()):
        resolvers[name] = {
            "env": sorted(getattr(resolver, "env", ())),
            "misses": sorted(getattr(resolver, "misses", ())),
            "position": DEFAULT_RESOLVER_ORDER.index(name) if name in DEFAULT_RESOLVER_ORDER else None,
            "working": bool(getattr(resolver, "working", True)),
        }
    lock_policies = {
        name: {"working": factory is not CopyOnLockPolicy, "env": sorted({LOCK_POLICY_ENV} | ({LOCK_WAIT_ENV} if factory is WaitBoundedLockPolicy else set()))}
        for name, factory in sorted(LOCK_POLICIES.items())
    }
    accesses = {
        name: {"working": not isinstance(access, SnapshotRepositoryAccess), "env": [REPOSITORY_ACCESS_ENV]}
        for name, access in sorted(REPOSITORY_ACCESS.items())
    }
    return {
        "default_order": list(DEFAULT_RESOLVER_ORDER),
        "env": sorted({ORDER_ENV, MAP_ENV, RESET_OWNER_ENV, LOCK_POLICY_ENV, LOCK_WAIT_ENV, REPOSITORY_ACCESS_ENV}),
        "lock_policies": lock_policies,
        "repository_access": accesses,
        "resolvers": resolvers,
        "walker_misses": list(WALKER_MISSES),
    }


def close_resolvers() -> dict:
    """Release anything a resolver holds open (analysis projects). Idempotent."""
    out: dict = {}
    for name, resolver in sorted(RAW_IMAGE_RESOLVERS.items()):
        close = getattr(resolver, "close", None)
        if callable(close):
            out[name] = close()
    return out


def write_bytes_atomic(target: Path, data: bytes) -> None:
    """Write *data* to *target* through a temp file, fsync, atomic rename."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".raw-", suffix=".tmp", dir=str(target.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
        _fsync_dir(target.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


__all__ = [
    "RawImage",
    "RawImageError",
    "RawImageMiss",
    "RawImageResolver",
    "RepositoryAccess",
    "ServerRepositoryAccess",
    "LocalProjectAccess",
    "SnapshotRepositoryAccess",
    "REPOSITORY_ACCESS",
    "repository_access",
    "LockPolicy",
    "RefuseLockPolicy",
    "WaitBoundedLockPolicy",
    "CopyOnLockPolicy",
    "LOCK_POLICIES",
    "lock_policy",
    "RAW_IMAGE_RESOLVERS",
    "DEFAULT_RESOLVER_ORDER",
    "WALKER_MISSES",
    "describe_resolvers",
    "resolver_order",
    "resolve_raw_image",
    "row_context",
    "raw_image_target",
    "raw_image_root",
    "stream_sha256",
    "atomic_copy",
    "close_resolvers",
    "last_misses",
    "sha12",
    "write_bytes_atomic",
]
