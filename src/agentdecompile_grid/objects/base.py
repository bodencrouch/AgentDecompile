"""agentdecompile_grid.objects.base — helpers and extension protocols shared by every store adapter.

What lives here:

* **Ref and name validation.**  A ref is ``sha256:<64 lowercase hex>``; a named pointer is a
  ``/``-joined path of ``[A-Za-z0-9._-]`` segments with no ``..``, no leading ``/`` and no
  segment starting with ``.`` (so temp files, locks and markers can never collide with a name).
* **Sharded layout.**  ``objects/<hex[:w]>/<hex[w:2w]>/<hex>`` with ``shard_width`` hex
  characters per level and ``shard_depth`` levels; the full hex is always the file name.
* **Write-once put.**  Temp file in the same directory, fsync per policy, then either
  ``os.link`` (EEXIST = already present = no-op; true write-once) or ``os.replace``
  (filesystems without hard links).  A final path never holds partial bytes.
* **Extension protocols** the core ``ObjectStore`` Protocol does not include: ``NamedIndexStore``
  (enumerate names), ``EnumerableStore`` (stats, eviction, GC lock), ``PinRegistry`` (in-flight
  pins).  ``tasks.results`` needs ``NamedIndexStore``; ``objects.gc`` needs the other two.
* **Grid document convention** used by GC's pin walk: a JSON object with ``"refs": [ref, ...]``
  and/or ``"outputs": {name: ref}``.  Only those two keys are followed, only in documents the
  grid itself wrote under a named pointer (and, one level down, in the referents of those
  pointers).  Nothing else is content-sniffed.

Acceptance tests (named here, landed in the verification phase):

* ``test_atomic_write_once_link_is_noop_on_race`` — two writers of the same bytes: one file,
  both return, no temp leftovers.
* ``test_put_expect_mismatch_is_integrity_error`` — ``put(data, expect=other_ref)`` raises
  ``IntegrityError`` and writes nothing.
* ``test_validate_name_refuses_traversal`` — ``..``, absolute, empty segment and dot-prefixed
  segments raise ``InvalidName``.
"""
from __future__ import annotations

import contextlib
import dataclasses
import errno
import json
import os
import re
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, ContextManager, Iterable, Iterator, Mapping, Protocol, Sequence, runtime_checkable

from ..core import HASH_ALGORITHM, AlreadyOwned, GridError, NotConfigured, ObjectRef, ObjectStore, canonical_json, digest

REF_HEX_LEN = 64
REF_RE = re.compile(rf"^{HASH_ALGORITHM}:([0-9a-f]{{{REF_HEX_LEN}}})$")
REF_TOKEN_RE = re.compile(rf"{HASH_ALGORITHM}:[0-9a-f]{{{REF_HEX_LEN}}}")
NAME_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")
MAX_NAME_LEN = 512

OBJECTS_DIR = "objects"
NAMED_DIR = "named"
PINS_DIR = "pins"
INDEX_DIR = "index"
CORRUPT_DIR = "corrupt"
LAYOUT_FILE = "layout.json"
GC_LOCK_FILE = "gc.lock"
TEMP_PREFIX = ".tmp-"
LAYOUT_SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- errors
class InvalidRef(GridError):
    """Not a ``sha256:<64 hex>`` content address."""


class InvalidName(GridError):
    """A named pointer name that could escape ``named/`` or collide with store internals."""


class IntegrityError(GridError):
    """Bytes do not hash to the ref they were stored or requested under."""


class ObjectMissing(GridError, KeyError):
    """``get``/``size`` of a ref the store does not hold.  Also a ``KeyError`` for callers that expect one."""

    def __str__(self) -> str:  # KeyError quotes its argument; keep the message readable
        return GridError.__str__(self)


class ReadOnly(NotConfigured):
    """This adapter cannot accept writes here; the message names where writes go instead."""


class StoreFull(GridError):
    """The local store is at its size cap and GC could not free enough unpinned bytes."""

    exit_code = 5


class LayoutMismatch(GridError):
    """The store on disk was created with a different shard layout than the configuration asks for."""


# --------------------------------------------------------------------------- validation
def validate_ref(ref: str) -> ObjectRef:
    if not isinstance(ref, str) or not REF_RE.match(ref):
        raise InvalidRef(f"not a {HASH_ALGORITHM}:<{REF_HEX_LEN} hex> ref: {ref!r}")
    return ObjectRef(ref)


def is_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(REF_RE.match(value))


def ref_prefix_hex(prefix: str) -> str:
    """Normalise a listing prefix: ``sha256:ab`` or ``ab`` -> ``ab``; refuse non-hex."""
    hexpart = prefix.split(":", 1)[1] if ":" in prefix else prefix
    hexpart = hexpart.lower()
    if hexpart and not re.fullmatch(r"[0-9a-f]{1,%d}" % REF_HEX_LEN, hexpart):
        raise InvalidRef(f"listing prefix must be hex: {prefix!r}")
    return hexpart


def validate_name(name: str) -> str:
    """Return the normalised name (single slashes, no trailing slash) or raise ``InvalidName``."""
    if not isinstance(name, str) or not name:
        raise InvalidName("named pointer name must be a non-empty string")
    if len(name) > MAX_NAME_LEN:
        raise InvalidName(f"named pointer name longer than {MAX_NAME_LEN} characters")
    if name.startswith("/") or "\\" in name or "\x00" in name:
        raise InvalidName(f"named pointer name must be relative and use '/' only: {name!r}")
    segments = [s for s in name.split("/")]
    if any(s == "" for s in segments):
        raise InvalidName(f"named pointer name has an empty segment: {name!r}")
    for seg in segments:
        if seg in (".", "..") or not NAME_SEGMENT_RE.match(seg):
            raise InvalidName(f"named pointer segment {seg!r} is not [A-Za-z0-9_-][A-Za-z0-9._-]* (no '.', '..', leading dot)")
    return "/".join(segments)


def validate_owner(owner: str) -> str:
    """A pin owner is one name segment (a node key id, a task id, a process tag)."""
    if not isinstance(owner, str) or not NAME_SEGMENT_RE.match(owner) or owner in (".", ".."):
        raise InvalidName(f"pin owner must be one [A-Za-z0-9_-][A-Za-z0-9._-]* segment: {owner!r}")
    return owner


# --------------------------------------------------------------------------- layout
class FsyncPolicy(str, Enum):
    NONE = "none"
    DATA = "data"
    FULL = "full"


def shard_parts(hexdigest: str, width: int, depth: int) -> tuple[str, ...]:
    """Directory components for a hex digest: ``("ab", "cd")`` for width 2 depth 2."""
    if width <= 0 or depth <= 0:
        return ()
    return tuple(hexdigest[i * width:(i + 1) * width] for i in range(depth))


def object_relpath(ref: ObjectRef, width: int, depth: int) -> str:
    hexdigest = validate_ref(ref).hex
    return "/".join((OBJECTS_DIR, *shard_parts(hexdigest, width, depth), hexdigest))


@dataclass(frozen=True)
class Layout:
    """What is frozen per store on disk (``layout.json``) or per bucket prefix."""

    hash_algorithm: str = HASH_ALGORITHM
    shard_width: int = 2
    shard_depth: int = 1
    schema: int = LAYOUT_SCHEMA_VERSION

    def to_json(self) -> bytes:
        return canonical_json(dataclasses.asdict(self))

    @classmethod
    def from_json(cls, data: bytes) -> "Layout":
        rec = json.loads(data.decode("utf-8"))
        return cls(hash_algorithm=str(rec.get("hash_algorithm", HASH_ALGORITHM)),
                   shard_width=int(rec.get("shard_width", 2)), shard_depth=int(rec.get("shard_depth", 1)),
                   schema=int(rec.get("schema", LAYOUT_SCHEMA_VERSION)))

    def relpath(self, ref: ObjectRef) -> str:
        return object_relpath(ref, self.shard_width, self.shard_depth)

    def check(self, other: "Layout", where: str) -> None:
        if (self.hash_algorithm, self.shard_width, self.shard_depth) != (other.hash_algorithm, other.shard_width, other.shard_depth):
            raise LayoutMismatch(
                f"{where} was created with hash={self.hash_algorithm} shard_width={self.shard_width} "
                f"shard_depth={self.shard_depth}; configuration asks for hash={other.hash_algorithm} "
                f"shard_width={other.shard_width} shard_depth={other.shard_depth}. Set objects.shard_width/"
                f"shard_depth to the existing values or point paths.objects at a new directory.")


# --------------------------------------------------------------------------- atomic file helpers
def fsync_path(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_temp(directory: str, data: bytes, tag: str, fsync: FsyncPolicy) -> str:
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, f"{TEMP_PREFIX}{tag}-{os.getpid()}-{secrets.token_hex(4)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            if fsync is not FsyncPolicy.NONE:
                os.fsync(fh.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return tmp


def atomic_write_once(final_path: str, data: bytes, *, fsync: FsyncPolicy = FsyncPolicy.DATA,
                      strategy: str = "link", tag: str = "obj") -> bool:
    """Write ``data`` to ``final_path`` unless it already exists.  Returns True when this call wrote it.

    ``strategy="link"``: ``os.link(tmp, final)``; ``EEXIST`` means another writer won and the temp
    is discarded.  ``strategy="replace"``: ``os.replace`` (last writer wins; only for filesystems
    without hard links).  When ``link`` is unsupported by the filesystem (``EPERM``/``ENOTSUP``/
    ``EOPNOTSUPP``/``EXDEV``), the call falls back to ``replace`` for that write.
    """
    if os.path.exists(final_path):
        return False
    directory = os.path.dirname(final_path)
    tmp = _write_temp(directory, data, tag, fsync)
    try:
        if strategy == "link":
            try:
                os.link(tmp, final_path)
                written = True
            except FileExistsError:
                written = False
            except OSError as exc:
                if exc.errno in (errno.EPERM, errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP), errno.EXDEV, errno.EMLINK):
                    if os.path.exists(final_path):
                        written = False
                    else:
                        os.replace(tmp, final_path)
                        written = True
                        tmp = ""
                else:
                    raise
        elif strategy == "replace":
            if os.path.exists(final_path):
                written = False
            else:
                os.replace(tmp, final_path)
                written = True
                tmp = ""
        else:
            raise NotConfigured(f"unknown write_once_strategy {strategy!r}; use 'link' or 'replace'")
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    if written and fsync is FsyncPolicy.FULL:
        fsync_path(directory)
    return written


def atomic_replace(final_path: str, data: bytes, *, fsync: FsyncPolicy = FsyncPolicy.DATA, tag: str = "named") -> None:
    """Atomically replace ``final_path`` with ``data`` (named pointers: mutable, never torn)."""
    directory = os.path.dirname(final_path)
    tmp = _write_temp(directory, data, tag, fsync)
    try:
        os.replace(tmp, final_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    if fsync is FsyncPolicy.FULL:
        fsync_path(directory)


def is_temp_name(filename: str) -> bool:
    return filename.startswith(TEMP_PREFIX)


class ExclusiveFileLock:
    """Non-blocking exclusive lock on a file; a live holder makes acquisition raise ``AlreadyOwned``.

    Never blocks and never silently skips: exclusive lock is not join.
    """

    def __init__(self, path: str, what: str = "lock") -> None:
        self.path = path
        self.what = what
        self._fd: int | None = None

    def __enter__(self) -> "ExclusiveFileLock":
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, PermissionError):
                os.close(fd)
                raise AlreadyOwned(f"{self.what} at {self.path} is held by a live owner; attach to it or wait, never restart") from None
        except ImportError:  # pragma: no cover - non-POSIX fallback
            os.close(fd)
            try:
                fd = os.open(self.path + ".excl", os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o644)
            except FileExistsError:
                raise AlreadyOwned(f"{self.what} at {self.path}.excl exists; another owner holds it") from None
        self._fd = fd
        os.write(fd, str(os.getpid()).encode("ascii"))
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._fd is not None:
            with contextlib.suppress(OSError):
                os.ftruncate(self._fd, 0)
            os.close(self._fd)
            self._fd = None
            with contextlib.suppress(OSError):
                os.unlink(self.path + ".excl")


# --------------------------------------------------------------------------- extension protocols
@dataclass(frozen=True)
class ObjectStat:
    ref: ObjectRef
    size: int
    mtime: float
    atime: float


@runtime_checkable
class NamedIndexStore(Protocol):
    """A store that can enumerate and delete named pointers (needed by ``tasks.results`` and GC)."""

    def list_named(self, prefix: str = "") -> Iterator[str]: ...
    def delete_named(self, name: str) -> bool: ...


def can_list_named(store: Any) -> bool:
    """True when ``store`` can enumerate named pointers *here* (protocol shape and, for composites, a capable layer)."""
    if not isinstance(store, NamedIndexStore):
        return False
    probe = getattr(store, "can_list_named", None)
    return bool(probe()) if callable(probe) else True


@runtime_checkable
class EnumerableStore(Protocol):
    """A store GC can measure and evict from."""

    def stat(self, ref: ObjectRef) -> ObjectStat: ...
    def iter_stats(self) -> Iterator[ObjectStat]: ...
    def usage(self) -> tuple[int, int]: ...          # (bytes, count)
    def evict(self, ref: ObjectRef) -> int: ...       # bytes freed (0 if absent)
    def gc_lock(self) -> ContextManager[Any]: ...


@runtime_checkable
class PinRegistry(Protocol):
    """In-flight pins: a worker pins the refs of a task before it runs and unpins after."""

    def pin(self, owner: str, refs: Iterable[ObjectRef]) -> list[ObjectRef]: ...   # returns refs *not* present
    def unpin(self, owner: str) -> None: ...
    def pinned_refs(self) -> Iterator[ObjectRef]: ...
    def pins(self) -> Mapping[str, Sequence[ObjectRef]]: ...


# --------------------------------------------------------------------------- grid documents
def refs_in_document(data: bytes, *, max_bytes: int) -> list[ObjectRef]:
    """Refs a grid document names: a bare ref, or JSON with ``refs`` (list) / ``outputs`` (mapping) keys.

    Anything else (non-JSON, other keys, oversize) yields nothing: the walk follows schema, not content.
    """
    if len(data) > max_bytes:
        return []
    text = data.strip()
    if is_ref(text.decode("ascii", "replace")):
        return [ObjectRef(text.decode("ascii"))]
    try:
        doc = json.loads(text.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    if not isinstance(doc, dict):
        return []
    found: set[ObjectRef] = set()
    refs = doc.get("refs")
    if isinstance(refs, list):
        found.update(ObjectRef(r) for r in refs if is_ref(r))
    outputs = doc.get("outputs")
    if isinstance(outputs, dict):
        found.update(ObjectRef(r) for r in outputs.values() if is_ref(r))
    single = doc.get("ref")
    if is_ref(single):
        found.add(ObjectRef(single))
    return sorted(found)


# --------------------------------------------------------------------------- schema helper
def schema_from_dataclass(cls: type, *, title: str = "") -> dict[str, Any]:
    """A JSON-schema-like description generated from a config dataclass and its field docs."""
    props: dict[str, Any] = {}
    for f in fields(cls):
        if f.metadata.get("internal"):
            continue
        default = f.default if f.default is not dataclasses.MISSING else (
            f.default_factory() if f.default_factory is not dataclasses.MISSING else None)  # type: ignore[misc]
        if is_dataclass(default):
            props[f.name] = schema_from_dataclass(type(default), title=f.name)
            continue
        if isinstance(default, bool):
            typ: Any = "boolean"
        elif isinstance(default, int):
            typ = "integer"
        elif isinstance(default, float):
            typ = "number"
        elif isinstance(default, tuple):
            typ = "array"
        elif isinstance(default, Mapping):
            typ = "object"
        else:
            typ = "string"
        entry: dict[str, Any] = {"type": typ, "default": list(default) if isinstance(default, tuple) else default}
        if f.metadata.get("doc"):
            entry["description"] = f.metadata["doc"]
        if typ == "array":
            entry["items"] = {"type": "string"}
        props[f.name] = entry
    return {"type": "object", "title": title or cls.__name__, "properties": props, "additionalProperties": False}


# --------------------------------------------------------------------------- base adapter
class BaseObjectStore(ABC):
    """Common surface of every adapter: ``name``, ``kind``, ``status``, ``config_schema``, ``describe()``.

    Subclasses implement the core ``ObjectStore`` Protocol; the helpers here add value/ref
    conveniences and read-side integrity checks.
    """

    name: str = "base"
    kind: str = "object-store"
    status: str = "declared"          # "working" | "declared"
    config_schema: Mapping[str, Any] = {"type": "object", "properties": {}}
    verify_on_read: bool = True

    # ---- core protocol (abstract) ----------------------------------------------------------
    @abstractmethod
    def put(self, data: bytes, *, expect: ObjectRef | None = None) -> ObjectRef: ...

    @abstractmethod
    def get(self, ref: ObjectRef) -> bytes: ...

    @abstractmethod
    def exists(self, ref: ObjectRef) -> bool: ...

    @abstractmethod
    def list(self, prefix: str = "") -> Iterator[ObjectRef]: ...

    @abstractmethod
    def size(self, ref: ObjectRef) -> int: ...

    @abstractmethod
    def put_named(self, name: str, data: bytes) -> None: ...

    @abstractmethod
    def get_named(self, name: str) -> bytes | None: ...

    # ---- shared conveniences --------------------------------------------------------------
    def put_value(self, value: Any) -> ObjectRef:
        """Store a canonical-JSON document."""
        return self.put(canonical_json(value))

    def get_value(self, ref: ObjectRef) -> Any:
        return json.loads(self.get(ref).decode("utf-8"))

    def put_named_ref(self, name: str, ref: ObjectRef) -> None:
        self.put_named(name, str(validate_ref(ref)).encode("ascii"))

    def get_named_ref(self, name: str) -> ObjectRef | None:
        data = self.get_named(name)
        if data is None:
            return None
        text = data.decode("ascii", "replace").strip()
        if not is_ref(text):
            raise IntegrityError(f"named pointer {name!r} does not hold a ref: {text[:80]!r}")
        return ObjectRef(text)

    def check_integrity(self, ref: ObjectRef, data: bytes) -> bytes:
        """Raise ``IntegrityError`` when ``data`` does not hash to ``ref`` (when ``verify_on_read``)."""
        if self.verify_on_read:
            actual = digest(data)
            if actual != validate_ref(ref).hex:
                raise IntegrityError(f"{self.name}: object {ref} hashed to {HASH_ALGORITHM}:{actual} on read")
        return data

    @staticmethod
    def expected_ref(data: bytes, expect: ObjectRef | None) -> ObjectRef:
        """The ref ``data`` must be stored under; refuse a caller-supplied ref that does not match."""
        actual = ObjectRef.of_bytes(data)
        if expect is not None and validate_ref(expect) != actual:
            raise IntegrityError(f"put(expect={expect}) but the bytes hash to {actual}; refusing to store under the wrong ref")
        return actual

    # ---- streaming defaults (adapters with a real fast path override these) ----------------
    def put_path(self, path: str | os.PathLike[str], *, expect: ObjectRef | None = None, link: bool = True) -> ObjectRef:
        """Store a file.  The default reads it into memory; ``LocalDirStore`` streams and links."""
        with open(path, "rb") as fh:
            return self.put(fh.read(), expect=expect)

    def get_path(self, ref: ObjectRef, dest: str | os.PathLike[str], *, link: bool = True) -> str:
        """Write an object to ``dest``.  The default goes through ``get``; ``LocalDirStore`` links."""
        dest = os.fspath(dest)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        data = self.get(ref)
        with open(dest, "wb") as fh:
            fh.write(data)
        return dest

    # ---- locators ------------------------------------------------------------------------
    @classmethod
    def from_locator(cls, locator: Mapping[str, Any]) -> "BaseObjectStore":
        """Build from a serialisable ``{"adapter": <name>, ...}`` mapping (what a sandbox child gets).
        Adapters that can be located override this; the default names the gap."""
        raise NotConfigured(f"object store adapter {cls.name!r} cannot be built from a locator; "
                            f"construct it with from_config(GridConfig) or directly")

    def describe(self) -> dict[str, Any]:
        """What the CLI prints for this adapter.  Subclasses extend with their own settings."""
        return {"name": self.name, "kind": self.kind, "status": self.status, "class": type(self).__name__,
                "verify_on_read": bool(self.verify_on_read)}

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"


def describe_store(store: ObjectStore) -> dict[str, Any]:
    """``describe()`` for any store, including foreign ones that only meet the core Protocol."""
    if hasattr(store, "describe"):
        return dict(store.describe())  # type: ignore[attr-defined]
    return {"name": getattr(store, "name", type(store).__name__), "kind": "object-store", "status": "foreign",
            "class": type(store).__name__}


__all__ = [
    "REF_RE", "REF_TOKEN_RE", "REF_HEX_LEN", "OBJECTS_DIR", "NAMED_DIR", "PINS_DIR", "INDEX_DIR", "CORRUPT_DIR",
    "LAYOUT_FILE", "GC_LOCK_FILE", "TEMP_PREFIX",
    "InvalidRef", "InvalidName", "IntegrityError", "ObjectMissing", "ReadOnly", "StoreFull", "LayoutMismatch",
    "validate_ref", "is_ref", "ref_prefix_hex", "validate_name", "validate_owner",
    "FsyncPolicy", "shard_parts", "object_relpath", "Layout",
    "fsync_path", "atomic_write_once", "atomic_replace", "is_temp_name", "ExclusiveFileLock",
    "ObjectStat", "NamedIndexStore", "EnumerableStore", "PinRegistry", "can_list_named",
    "refs_in_document", "schema_from_dataclass", "BaseObjectStore", "describe_store",
]
