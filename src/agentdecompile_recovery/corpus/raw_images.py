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
image in memory: a resolver that produces bytes (the analysis project's
stored file bytes) spools them to a temporary file while hashing, and the
walker moves or copies that file into place.
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


class GhidraFileBytesResolver:
    """Re-materialize the image from the analysis project's stored file bytes.

    Candidates: the row's ``repo_path`` when it is a project file, then each
    ``program_bindings`` entry (locator + program path). The project is
    opened with ``resetOwner=False`` so a live session keeps its lock (a
    held lock is the miss ``ghidra_project_locked``); the program is opened
    read-only; nothing is saved. Exactly one ``FileBytes`` entry is required
    -- several is ``ambiguous_file_bytes``, because a guessed concatenation
    would produce a permanent wrong hash (R3 never clears a stored value).

    All analyzer work runs on one long-lived daemon thread and is waited on
    with ``future.result(timeout=deadline_s)``. Opened projects are kept
    until :meth:`close` so one project serves every row bound to it. After
    the first timeout the resolver reports ``ghidra_deadline`` for the rest
    of the process instead of paying the deadline again per row. When the
    analyzer bridge is not importable the miss is ``ghidra_unavailable``;
    when no candidate project exists it is ``ghidra_project_missing``.
    """

    name = "ghidra_file_bytes"

    def __init__(self) -> None:
        self._worker: _DaemonWorker | None = None
        self._projects: dict[tuple[str, str], object] = {}
        self._unavailable: str | None = None
        self._lock = threading.Lock()

    # -- candidates ---------------------------------------------------------

    @staticmethod
    def _candidates(row: dict) -> tuple[list[tuple[Path, str, str | None]], set[str]]:
        """``[(project_dir, project_name, program_path|None)]`` and skip reasons."""
        out: list[tuple[Path, str, str | None]] = []
        skipped: set[str] = set()
        repo = str(row.get("repo_path") or "")
        if repo.lower().endswith(".gpr"):
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
        with self._lock:
            if self._worker is None:
                self._worker = _DaemonWorker("raw-image-ghidra")
            return self._worker.submit(fn)

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        if self._unavailable:
            raise RawImageMiss(self._unavailable)
        candidates, skipped = self._candidates(row)
        if not candidates:
            raise RawImageMiss(sorted(skipped)[0] if skipped else "ghidra_no_binding")
        repo = str(row.get("repo_path") or "")
        future = self._submit(lambda: self._read(candidates, repo, deadline_s))
        try:
            result = future.result(timeout=max(0.0, float(deadline_s)))
        except concurrent.futures.TimeoutError:
            self._unavailable = "ghidra_deadline"
            raise RawImageMiss("ghidra_deadline") from None
        if isinstance(result, RawImageMiss):
            if result.reason == "ghidra_unavailable":
                self._unavailable = result.reason
            raise result
        image, provenance = result
        for name in sorted(skipped):
            provenance.setdefault("skipped_locators", []).append(name)
        return RawImage(None, image[0], image[1], image[2], self.name, provenance)

    # -- analyzer side (worker thread only) ---------------------------------

    def _open_project(self, project_dir: Path, project_name: str) -> tuple[object | None, str | None]:
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
        try:
            if os.environ.get(RESET_OWNER_ENV, "").strip() == "1":
                from ghidra.pyghidra import PyGhidraProjectManager  # type: ignore[import-not-found]

                project = PyGhidraProjectManager().openProject(
                    ProjectLocator(str(project_dir), project_name), False, True
                )
                project = _GhidraProjectShim(project)
            else:
                project = GhidraProject.openProject(str(project_dir), project_name, False)
        except Exception as exc:  # LockException / NotOwnerException / IOException
            text = type(exc).__name__ + ":" + str(exc)
            if "Lock" in text or "Owner" in text or "lock" in str(exc).lower():
                return None, "ghidra_project_locked"
            return None, "ghidra_project_open_error"
        self._projects[key] = project
        return project, None

    def _read(self, candidates, repo: str, deadline_s: float):
        deadline = time.monotonic() + float(deadline_s)
        try:
            import pyghidra  # type: ignore[import-not-found]
        except ImportError:
            return RawImageMiss("ghidra_unavailable")
        try:
            if not pyghidra.started():
                pyghidra.start()
        except Exception:
            return RawImageMiss("ghidra_unavailable")
        reasons: list[str] = []
        basename = Path(repo).name.casefold()
        for project_dir, project_name, program_path in candidates:
            if time.monotonic() > deadline:
                return RawImageMiss("ghidra_deadline")
            project, why = self._open_project(project_dir, project_name)
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
                    outcome = self._spool(program, deadline)
                finally:
                    try:
                        project.close(program)
                    except Exception:
                        pass
                if isinstance(outcome, str):
                    reasons.append(outcome)
                    continue
                spool, digest, size, filename_sha12 = outcome
                provenance = {
                    "locator_kind": "ghidra_project",
                    "project_sha12": sha12(str(project_dir / project_name)),
                    "program_sha12": sha12(ppath),
                    "file_bytes_name_sha12": filename_sha12,
                    "spooled": True,
                }
                return (spool, digest, size), provenance
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

    @staticmethod
    def _spool(program, deadline: float):
        """Stream the program's single FileBytes into a temp file; return
        ``(path, sha256, size, filename_sha12)`` or a miss reason."""
        try:
            entries = list(program.getMemory().getAllFileBytes())
        except Exception:
            return "ghidra_file_bytes_error"
        if len(entries) != 1:
            return "ambiguous_file_bytes" if entries else "no_file_bytes"
        fb = entries[0]
        try:
            import jpype  # type: ignore[import-not-found]

            total = int(fb.getSize())
            buf = jpype.JArray(jpype.JByte)(CHUNK)
        except Exception:
            return "ghidra_file_bytes_error"
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
            return "ghidra_deadline"
        except Exception:
            tmp.unlink(missing_ok=True)
            return "ghidra_file_bytes_error"
        if size != total:
            tmp.unlink(missing_ok=True)
            return "ghidra_file_bytes_short"
        try:
            fname = str(fb.getFilename())
        except Exception:
            fname = ""
        return tmp, h.hexdigest(), size, sha12(fname)

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

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        raise NotImplementedError("A4.object_store")


class PeerFetchResolver:
    """Slot: fetch the image from a peer node by content hash.

    Contract: outbound-only HTTP to a configured peer list, verifying the
    returned bytes against the requested sha256 before returning a path.
    Never trusts a peer's claimed hash.
    """

    name = "peer_fetch"

    def resolve(self, row: dict, *, work_dir: Path | None, deadline_s: float) -> RawImage | None:
        raise NotImplementedError("A4.peer_fetch")


class ArchiveMemberResolver:
    """Slot: an image inside a corpus ZIP, located through ``archive.py``.

    Contract: given an archive path from configuration and the row's
    ``repo_path`` as the member name, extract that member to a temp file
    (streamed) and return its path; ``member_missing`` otherwise.
    """

    name = "archive_member"

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
        GhidraFileBytesResolver(),
        ObjectStoreResolver(),
        PeerFetchResolver(),
        ArchiveMemberResolver(),
    )
}

#: Working resolvers, cheapest first. Slots are registered but not walked.
DEFAULT_RESOLVER_ORDER: tuple[str, ...] = (
    "extract_raw_dir",
    "repo_path_file",
    "explicit_map",
    "content_identity_table",
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
    "RAW_IMAGE_RESOLVERS",
    "DEFAULT_RESOLVER_ORDER",
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
