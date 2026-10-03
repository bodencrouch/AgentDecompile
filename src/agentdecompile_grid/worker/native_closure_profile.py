"""Owner-pinned native root descriptions and private byte-copy primitives.

This is NOT a sandbox, admission reader or execution receipt. No import-time I/O
occurs. The future supervisor must own both supplied directory descriptors, run
capture in its one owned helper process, enforce later phase reservations, and
exclude unrelated unconfined writers under its UID. Filesystem calls can block
beyond the cooperative deadline. A mode-0700 parent does not prove that domain.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

PROFILE_ID = "linux-x86_64-native-objdiff-region-runtime-v1"
PROFILE_SCHEMA = "agentdecompile.native-closure-profile.v1"
INVENTORY_SCHEMA = "agentdecompile.native-root-inventory.v1"
SOURCE_SCHEMA = "agentdecompile.native-source-inventory.v1"
POLICY_ID = "linux-x86_64-native-closure-policy-v1"
MAX_PROFILE_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 16_384
MAX_PATH_BYTES = 512
MAX_DEPTH = 24
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
CAPTURE_SECONDS = 90.0
ENVIRONMENT = (
    ("AGENT_DECOMPILE_OBJDIFF", "/tools/objdiff"), ("HOME", "/work/home"),
    ("LANG", "C"), ("LC_ALL", "C"), ("PATH", "/tools"),
    ("TMPDIR", "/work/tmp"), ("TZ", "UTC"),
)


class ProfileRefused(ValueError):
    """A fixed refusal code with diagnostic detail; never a producer refutation."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _refuse(detail: str, code: str = "root_layout_unsupported") -> None:
    raise ProfileRefused(code, detail)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fields(value: Any, names: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(names.split()):
        _refuse("missing, unknown or non-object fields")
    return value


def _string(value: Any, cap: int = MAX_PATH_BYTES) -> str:
    if type(value) is not str or not value or "\x00" in value:
        _refuse("expected nonempty NUL-free string")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeError:
        _refuse("invalid Unicode scalar string")
    if len(encoded) > cap:
        _refuse("string limit exceeded", "limit_exceeded")
    return value


def _digest(value: Any) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _refuse("expected lowercase SHA-256")
    return value


def _uint(value: Any, cap: int) -> int:
    if type(value) is not int or value < 0 or value > cap:
        _refuse("integer outside fixed bound", "limit_exceeded")
    return value


def _path(value: Any) -> str:
    value = _string(value)
    parts = value.split("/")
    if len(parts) > MAX_DEPTH or any(p in ("", ".", "..") for p in parts):
        _refuse("non-relative, non-normalized or too-deep path")
    # No backslash ambiguity for other consumers, even on this Linux profile.
    if "\\" in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        _refuse("control character or backslash in path")
    return value


def _decode(raw: bytes, cap: int, expected: str) -> dict[str, Any]:
    _digest(expected)
    if type(raw) is not bytes or len(raw) > cap:
        _refuse("document byte limit", "limit_exceeded")
    if _hash(raw) != expected:
        _refuse("owner document pin mismatch", "profile_pin_mismatch")
    # Bound container/node allocations BEFORE json.loads. All accepted schemas
    # have depth <= 3, <= entries+16 objects and <= 2 arrays. This small lexical
    # preflight ignores punctuation inside strings; json.loads checks grammar.
    depth = objects = arrays = separators = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (123, 91):
            depth += 1
            objects += byte == 123
            arrays += byte == 91
            if depth > 8 or objects > MAX_ENTRIES + 16 or arrays > 16:
                _refuse("JSON container allocation limit", "limit_exceeded")
        elif byte in (125, 93):
            depth -= 1
        elif byte in (44, 58):
            separators += 1
            if separators > MAX_ENTRIES * 16 + 256:
                _refuse("JSON member allocation limit", "limit_exceeded")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _refuse("duplicate JSON key")
            result[key] = value
        return result

    def no_number(value: str) -> Any:
        _refuse("floating point/nonfinite numbers are unsupported")

    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
                           parse_constant=no_number, parse_float=no_number)
        if type(value) is not dict or _canonical(value) != raw:
            _refuse("noncanonical JSON")
    except ProfileRefused:
        raise
    except (UnicodeError, RecursionError, ValueError, OverflowError) as exc:
        raise ProfileRefused("root_layout_unsupported", "invalid bounded JSON") from exc
    return value


@dataclass(frozen=True)
class InventoryEntry:
    path: str
    type: str
    permission_class: str
    size: int | None = None
    sha256: str | None = None
    target: str | None = None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"path": self.path, "type": self.type,
                                  "permission_class": self.permission_class}
        if self.type == "file":
            record.update(size=self.size, sha256=self.sha256)
        elif self.type == "symlink":
            record["target"] = self.target
        return record


@dataclass(frozen=True)
class RootInventory:
    canonical_bytes: bytes
    sha256: str
    entries: tuple[InventoryEntry, ...]
    total_file_bytes: int


@dataclass(frozen=True)
class NativeProfile:
    canonical_bytes: bytes
    sha256: str
    inventory: RootInventory
    implementation_source_sha256: str
    interpreter_sha256: str
    entrypoint_sha256: str
    checker_id: str
    checker_sha256: str
    launcher_sha256: str
    filter_sha256: str
    environment_sha256: str


def _resolve(path: str, entries: dict[str, InventoryEntry]) -> str:
    """Resolve a declared path inside the final root, never using host realpath."""
    pending = deque(path.split("/"))
    resolved: list[str] = []
    visited: set[str] = set()
    while pending:
        part = pending.popleft()
        if part in ("", "."):
            continue
        if part == "..":
            if not resolved:
                _refuse("symlink escapes root")
            resolved.pop()
            continue
        candidate = "/".join((*resolved, part))
        entry = entries.get(candidate)
        if entry is None:
            _refuse("dangling symlink")
        if entry.type == "symlink":
            if candidate in visited or len(visited) >= 40:
                _refuse("cyclic or excessive symlink chain")
            visited.add(candidate)
            target = entry.target
            assert target is not None
            if target.startswith("/"):
                resolved.clear()
            pending.extendleft(reversed(target.split("/")))
        else:
            if pending and entry.type != "directory":
                _refuse("symlink traverses ordinary file")
            resolved.append(part)
        if len(pending) + len(resolved) > MAX_DEPTH * 2:
            _refuse("symlink resolution depth", "limit_exceeded")
    return "/".join(resolved)


def _check_links(entries: dict[str, InventoryEntry]) -> None:
    # Include ordinary containment edges: directory aliases must not create a
    # recursive cycle even when their individual symlink chains terminate.
    graph: dict[str, list[str]] = {"": []}
    for entry in entries.values():
        if entry.type == "directory":
            graph[entry.path] = []
    for entry in entries.values():
        parent = entry.path.rpartition("/")[0]
        if entry.type == "directory":
            graph[parent].append(entry.path)
        elif entry.type == "symlink":
            target = _resolve(entry.path, entries)
            if target in graph:
                graph[parent].append(target)
    indegree = dict.fromkeys(graph, 0)
    for children in graph.values():
        for child in children:
            indegree[child] += 1
    ready = deque(node for node, count in indegree.items() if count == 0)
    count = 0
    while ready:
        node = ready.popleft()
        count += 1
        for child in graph[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if count != len(graph):
        _refuse("directory symlink cycle")


def validate_inventory(raw: bytes, *, expected_sha256: str) -> RootInventory:
    """Pure bounded parser; the owner pin must come from supervisor authority."""
    document = _fields(_decode(raw, MAX_MANIFEST_BYTES, expected_sha256), "schema entries")
    if document["schema"] != INVENTORY_SCHEMA or type(document["entries"]) is not list:
        _refuse("inventory schema")
    rows = document["entries"]
    if not 0 < len(rows) <= MAX_ENTRIES:
        _refuse("entry count", "limit_exceeded")
    entries: dict[str, InventoryEntry] = {}
    previous = b""
    total = 0
    for row in rows:
        if type(row) is not dict:
            _refuse("entry must be an object")
        kind = row.get("type")
        extra = {"directory": "", "file": " size sha256", "symlink": " target"}.get(kind) if type(kind) is str else None
        if extra is None:
            _refuse("unsupported entry kind")
        _fields(row, "path type permission_class" + extra)
        path = _path(row["path"])
        encoded = path.encode("utf-8")
        if encoded <= previous:
            _refuse("paths must be unique and UTF-8 byte sorted")
        previous = encoded
        parent = path.rpartition("/")[0]
        if parent and (parent not in entries or entries[parent].type != "directory"):
            _refuse("missing or non-directory parent")
        permission = row["permission_class"]
        if kind == "file":
            if permission not in ("data", "executable"):
                _refuse("file permission class")
            size = _uint(row["size"], MAX_FILE_BYTES)
            total += size
            if total > MAX_TOTAL_BYTES:
                _refuse("aggregate file bytes", "limit_exceeded")
            entry = InventoryEntry(path, kind, permission, size, _digest(row["sha256"]))
        elif kind == "symlink":
            if permission != "symlink":
                _refuse("symlink permission class")
            target = _string(row["target"])
            if "\\" in target or any(ord(c) < 32 or ord(c) == 127 for c in target):
                _refuse("unsafe symlink target encoding")
            entry = InventoryEntry(path, kind, permission, target=target)
        else:
            if permission != "directory":
                _refuse("directory permission class")
            entry = InventoryEntry(path, kind, permission)
        basename = path.rsplit("/", 1)[-1]
        if (basename.endswith((".pyc", ".pyo", ".pth")) or basename in
                ("pyvenv.cfg", "sitecustomize.py", "usercustomize.py") or
                path in ("etc/ld.so.preload", "etc/ld.so.cache")):
            _refuse("prohibited Python/loader file")
        if path.startswith(("usr/lib/python3.12/", "app/")) and basename.endswith(".zip"):
            _refuse("zip imports unsupported in measured Python trees")
        entries[path] = entry
    _check_links(entries)
    return RootInventory(raw, expected_sha256, tuple(entries.values()), total)


def load_profile(profile_bytes: bytes, inventory_bytes: bytes, *,
                 expected_profile_sha256: str, expected_inventory_sha256: str) -> NativeProfile:
    """Pure parsing/binding; neither document is allowed to choose its own pin."""
    document = _fields(_decode(profile_bytes, MAX_PROFILE_BYTES, expected_profile_sha256),
                       "schema profile_id root_inventory_sha256 implementation_source_sha256 "
                       "interpreter entrypoint checker launcher policy environment environment_sha256 "
                       "supervisor_domain work_filesystem")
    if document["schema"] != PROFILE_SCHEMA or document["profile_id"] != PROFILE_ID:
        _refuse("unsupported profile family")
    if document["root_inventory_sha256"] != _digest(expected_inventory_sha256):
        _refuse("profile/inventory owner pins disagree", "profile_pin_mismatch")
    inventory = validate_inventory(inventory_bytes, expected_sha256=expected_inventory_sha256)
    entries = {entry.path: entry for entry in inventory.entries}
    interpreter = _fields(document["interpreter"], "path family sha256")
    entrypoint = _fields(document["entrypoint"], "path sha256")
    checker = _fields(document["checker"], "id path sha256")
    launcher = _fields(document["launcher"], "family source_version sha256")
    policy = _fields(document["policy"], "id filter_sha256")
    work = _fields(document["work_filesystem"], "flags max_bytes")
    if (interpreter["family"] != "cpython-3.12" or launcher["family"] != "bubblewrap"
            or launcher["source_version"] != "0.11.0" or policy["id"] != POLICY_ID
            or document["supervisor_domain"] != "dedicated-trusted-uid"
            or work["flags"] != ["noexec", "nosuid", "nodev"]
            or type(work["max_bytes"]) is not int or work["max_bytes"] != MAX_TOTAL_BYTES):
        _refuse("fixed family/policy/domain/work requirements differ")
    environment = _fields(document["environment"], " ".join(key for key, _ in ENVIRONMENT))
    if environment != dict(ENVIRONMENT):
        _refuse("environment override")
    environment_sha = _digest(document["environment_sha256"])
    if environment_sha != _hash(_canonical(environment)):
        _refuse("environment identity mismatch", "profile_pin_mismatch")
    for record, path, permission in ((interpreter, "/usr/bin/python3.12", "executable"),
                                     (entrypoint, "/app/native_closure_entry.py", "data"),
                                     (checker, "/tools/objdiff", "executable")):
        if record["path"] != path:
            _refuse("fixed runtime path override")
        entry = entries.get(path[1:])
        if (entry is None or entry.type != "file" or entry.permission_class != permission
                or entry.sha256 != _digest(record["sha256"])):
            _refuse("runtime artifact identity mismatch", "profile_pin_mismatch")
    for path in ("usr/lib/python3.12", "usr/lib/python3.12/lib-dynload", "app/src", "app/vendor", "work", "dev"):
        if path not in entries or entries[path].type != "directory":
            _refuse("required layout directory missing")
    null = entries.get("dev/null")
    if null != InventoryEntry("dev/null", "file", "data", 0, _hash(b"")):
        _refuse("dev/null must be an empty ordinary mount-point file")
    if any(e.path.startswith("work/") or (e.path.startswith("dev/") and e.path != "dev/null") for e in inventory.entries):
        _refuse("work must be empty; dev may contain only null mount point")
    source_entries = [e.to_record() for e in inventory.entries if e.path.startswith(("app/src/", "app/vendor/"))]
    if not any(e.type == "file" and e.path.startswith("app/src/") for e in inventory.entries):
        _refuse("source tree has no files")
    source_sha = _digest(document["implementation_source_sha256"])
    if _hash(_canonical({"schema": SOURCE_SCHEMA, "entries": source_entries})) != source_sha:
        _refuse("complete source subtree identity mismatch", "profile_pin_mismatch")
    return NativeProfile(profile_bytes, expected_profile_sha256, inventory, source_sha,
                         interpreter["sha256"], entrypoint["sha256"], _string(checker["id"], 256),
                         checker["sha256"], _digest(launcher["sha256"]),
                         _digest(policy["filter_sha256"]), environment_sha)


def describe_profile(profile: NativeProfile) -> dict[str, Any]:
    """No filesystem probe; a validated description is never launch authority."""
    return {"profile_id": PROFILE_ID, "profile_sha256": profile.sha256,
            "root_inventory_sha256": profile.inventory.sha256,
            "entry_count": len(profile.inventory.entries),
            "total_file_bytes": profile.inventory.total_file_bytes,
            "status": "source_primitives_only", "launch_available": False,
            "current_admission_available": False,
            "static_dependency_qualification": "pending"}


@dataclass(frozen=True)
class CaptureIdentity:
    profile_sha256: str
    inventory_sha256: str
    device: int
    inode: int
    mount_id: int


@dataclass
class OwnedAllocation:
    """Owned allocation handles, possibly partial; never execution evidence."""
    allocation_name: str
    root_fd: int
    parent_fd: int
    device: int
    inode: int
    mount_id: int

    def close(self) -> None:
        """Release handles only, without inferring that removal is safe."""
        for field in ("root_fd", "parent_fd"):
            fd = getattr(self, field)
            if fd >= 0:
                os.close(fd)
                setattr(self, field, -1)


@dataclass
class OwnedCapture(OwnedAllocation):
    """Successful frozen byte capture with read-only retained directory FDs.

    Never reconstruct this from JSON. It is NOT an execution/seal capability.
    Owner must keep the capture immutable until all future users exit; no
    launcher or automatic deletion is supplied here.
    """
    identity: CaptureIdentity


class CaptureFailed(ProfileRefused):
    """Fresh partial allocation is retained for supervisor-owned quarantine.

    No cleanup traversal is attempted after a failed/expired phase. The future
    helper lifecycle must confirm exit before bounded cleanup; it must never
    infer ownership from a runtime/digest path. None means allocation never began.
    """
    def __init__(self, code: str, detail: str, partial: OwnedAllocation | None) -> None:
        super().__init__(code, detail)
        self.partial = partial


@dataclass(frozen=True)
class _Budget:
    deadline: float

    def check(self) -> None:
        if time.monotonic() >= self.deadline:
            _refuse("cooperative capture deadline expired", "deadline_exceeded")


def _snapshot(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_uid,
            value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _mount_id(fd: int, budget: _Budget) -> int:
    """Linux FD anchor detects same-device bind mounts too; unavailable refuses."""
    budget.check()
    info = os.open(f"/proc/self/fdinfo/{fd}", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        data = os.read(info, 4097)
        if len(data) > 4096:
            _refuse("fdinfo cap", "limit_exceeded")
    finally:
        os.close(info)
    values = [line.split(b":", 1)[1].strip() for line in data.splitlines() if line.startswith(b"mnt_id:")]
    if len(values) != 1 or not values[0].isdigit():
        _refuse("retained descriptor mount identity unavailable")
    budget.check()
    return int(values[0])


def _xattrs(fd: int, budget: _Budget) -> None:
    budget.check()
    # listxattr is kernel-bounded (Linux's 64-KiB list limit). Unsupported or
    # denied enumeration refuses through capture's OSError handling.
    if any(name.startswith("security.") for name in os.listxattr(fd)):
        _refuse("security/capability xattr")
    budget.check()


def _mode(value: os.stat_result, kind: str) -> str:
    mode = value.st_mode
    if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
        _refuse("special permission bits")
    if kind == "directory":
        if not stat.S_ISDIR(mode) or mode & 0o500 != 0o500:
            _refuse("directory must be owner-readable/searchable")
        return "directory"
    if not stat.S_ISREG(mode) or value.st_nlink != 1:
        _refuse("non-regular file or hardlink")
    if mode & 0o111:
        if mode & 0o222:
            _refuse("writable executable")
        return "executable"
    return "data"


def _open_dir(parent: int, name: str, budget: _Budget) -> int:
    budget.check()
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)


def _names(fd: int, prefix: str, budget: _Budget, count: list[int]) -> list[str]:
    names: list[str] = []
    budget.check()
    with os.scandir(fd) as scan:
        for entry in scan:
            budget.check()
            if count[0] >= MAX_ENTRIES:
                _refuse("actual entry count", "limit_exceeded")
            _path(prefix + entry.name)
            count[0] += 1
            names.append(entry.name)
    return sorted(names, key=lambda name: name.encode("utf-8"))


def _same(before: os.stat_result, after: os.stat_result) -> None:
    if _snapshot(before) != _snapshot(after):
        _refuse("entry changed during capture", "capture_integrity_failed")


def _file(parent: int, name: str, entry: InventoryEntry, mount: int, budget: _Budget,
          destination: int | None, *, frozen: bool = False) -> None:
    budget.check()
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    # Pin without opening a device/FIFO for I/O. Reopen ONLY the retained regular
    # inode through trusted Linux procfs after fstat; never follow a donor link.
    anchor = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    fd = -1
    writer = -1
    try:
        _same(before, os.fstat(anchor))
        if _mode(before, "file") != entry.permission_class or before.st_size != entry.size:
            _refuse("file size/permission differs", "capture_integrity_failed")
        if frozen and stat.S_IMODE(before.st_mode) != (0o555 if entry.permission_class == "executable" else 0o444):
            _refuse("destination not frozen", "capture_integrity_failed")
        if _mount_id(anchor, budget) != mount:
            _refuse("file mount crossing")
        budget.check()
        fd = os.open(f"/proc/self/fd/{anchor}", os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        _same(before, os.fstat(fd))
        _xattrs(fd, budget)
        if destination is not None:
            budget.check()
            writer = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=destination)
            created = os.fstat(writer)
            if (created.st_dev, created.st_ino) == (before.st_dev, before.st_ino) or created.st_nlink != 1:
                _refuse("copy must have a distinct exclusive inode")
        hasher = hashlib.sha256()
        remaining = entry.size
        assert remaining is not None
        while remaining:
            budget.check()
            chunk = os.read(fd, min(CHUNK_BYTES, remaining))
            if not chunk:
                _refuse("short copy stream", "capture_integrity_failed")
            if writer >= 0:
                offset = 0
                while offset < len(chunk):
                    budget.check()
                    written = os.write(writer, memoryview(chunk)[offset:])
                    if written <= 0:
                        _refuse("short destination write", "capture_integrity_failed")
                    offset += written
            hasher.update(chunk)
            remaining -= len(chunk)
        budget.check()
        if os.read(fd, 1) or hasher.hexdigest() != entry.sha256:
            _refuse("copied bytes disagree with owner pin", "capture_integrity_failed")
        _xattrs(fd, budget)
        _same(before, os.fstat(fd))
        _same(before, os.stat(name, dir_fd=parent, follow_symlinks=False))
    finally:
        if writer >= 0:
            os.close(writer)
        if fd >= 0:
            os.close(fd)
        os.close(anchor)


def _walk(source: int, destination: int | None, prefix: str, entries: dict[str, InventoryEntry],
          mount: int, budget: _Budget, count: list[int], observed: list[InventoryEntry],
          *, staging: bool = False, frozen: bool = False) -> None:
    before = os.fstat(source)
    _mode(before, "directory")
    if frozen and stat.S_IMODE(before.st_mode) != 0o555:
        _refuse("destination directory not frozen", "capture_integrity_failed")
    if _mount_id(source, budget) != mount:
        _refuse("directory mount crossing")
    _xattrs(source, budget)
    for name in _names(source, prefix, budget, count):
        budget.check()
        path = prefix + name
        entry = entries.get(path)
        if entry is None:
            _refuse("extra root entry", "capture_integrity_failed")
        value = os.stat(name, dir_fd=source, follow_symlinks=False)
        if entry.type == "directory":
            _mode(value, "directory")
            child = _open_dir(source, name, budget)
            target = None
            try:
                _same(value, os.fstat(child))
                if destination is not None:
                    budget.check()
                    os.mkdir(name, 0o700, dir_fd=destination)
                    target = _open_dir(destination, name, budget)
                _walk(child, target, path + "/", entries, mount, budget, count, observed, staging=staging, frozen=frozen)
                _same(value, os.fstat(child))
                _same(value, os.stat(name, dir_fd=source, follow_symlinks=False))
            finally:
                if target is not None:
                    os.close(target)
                os.close(child)
        elif entry.type == "file":
            if staging:
                # Newly copied files remain 0600 until ALL write handles close.
                # Their measured executable class comes from the authenticated
                # donor, then is checked again after descriptor-relative freeze.
                staged_entry = InventoryEntry(entry.path, "file", "data", entry.size, entry.sha256)
                _file(source, name, staged_entry, mount, budget, None)
            else:
                _file(source, name, entry, mount, budget, destination, frozen=frozen)
        else:
            if not stat.S_ISLNK(value.st_mode) or value.st_nlink != 1:
                _refuse("symlink type/hardlink mismatch")
            link = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=source)
            try:
                _same(value, os.fstat(link))
                if _mount_id(link, budget) != mount:
                    _refuse("symlink mount crossing")
                # Linux O_PATH cannot listxattr. Retained parent path plus
                # no-follow llistxattr and lstat/ctime checks anchor this lookup.
                budget.check()
                attrs = os.listxattr(f"/proc/self/fd/{source}/{name}", follow_symlinks=False)
                if any(attr.startswith("security.") for attr in attrs):
                    _refuse("symlink security xattr")
                target_text = os.readlink("", dir_fd=link)
                if target_text != entry.target:
                    _refuse("symlink target mismatch", "capture_integrity_failed")
                _same(value, os.fstat(link))
                _same(value, os.stat(name, dir_fd=source, follow_symlinks=False))
                if destination is not None:
                    budget.check()
                    os.symlink(target_text, name, dir_fd=destination)
            finally:
                os.close(link)
        observed.append(entry)
    _xattrs(source, budget)
    _same(before, os.fstat(source))


def _verify_tree(root: int, inventory: RootInventory, budget: _Budget, *, staging: bool) -> None:
    observed: list[InventoryEntry] = []
    _walk(root, None, "", {e.path: e for e in inventory.entries}, _mount_id(root, budget),
          budget, [0], observed, staging=staging, frozen=not staging)
    budget.check()
    raw = _canonical({"schema": INVENTORY_SCHEMA,
                      "entries": [e.to_record() for e in sorted(observed, key=lambda e: e.path.encode("utf-8"))]})
    if raw != inventory.canonical_bytes or _hash(raw) != inventory.sha256:
        _refuse("complete captured inventory mismatch", "capture_integrity_failed")


def _freeze(root: int, children: dict[str, list[InventoryEntry]], prefix: str, budget: _Budget) -> None:
    # All copy writers were closed before this traversal. fchmod operates through
    # retained read-only FDs; never reopen a writable file for freezing.
    for entry in children.get(prefix, ()):
        budget.check()
        name = entry.path.rsplit("/", 1)[-1]
        if entry.type == "symlink":
            continue
        if entry.type == "directory":
            child = _open_dir(root, name, budget)
            try:
                _freeze(child, children, entry.path, budget)
            finally:
                os.close(child)
        else:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root)
            try:
                os.fchmod(fd, 0o555 if entry.permission_class == "executable" else 0o444)
            finally:
                os.close(fd)
    budget.check()
    os.fchmod(root, 0o555)


def capture_private(profile: NativeProfile, *, donor_fd: int, private_parent_fd: int,
                    absolute_deadline: float) -> OwnedCapture:
    """Fresh capture under trusted descriptor anchors; no caller-selected name.

    The supplied absolute deadline already reserves later lifecycle phases.
    Synchronous I/O can exceed it; call ONLY inside the future owned helper.
    Failure retains a freshly allocated partial in CaptureFailed.partial, never
    deletes someone else's directory and never reports successful cleanup.
    """
    try:
        finite = type(absolute_deadline) in (int, float) and math.isfinite(absolute_deadline)
    except OverflowError:
        finite = False
    if not finite:
        _refuse("deadline must be finite monotonic seconds", "deadline_exceeded")
    budget = _Budget(min(time.monotonic() + CAPTURE_SECONDS, absolute_deadline))
    budget.check()
    # Reparse immutable bytes at the authority boundary; public dataclass
    # constructors are convenience, not trusted proof of validation.
    checked = load_profile(profile.canonical_bytes, profile.inventory.canonical_bytes,
                           expected_profile_sha256=profile.sha256,
                           expected_inventory_sha256=profile.inventory.sha256)
    budget.check()
    partial: OwnedAllocation | None = None
    parent = -1
    root = -1
    donor = -1
    name: str | None = None
    try:
        parent = os.dup(private_parent_fd)
        os.set_inheritable(parent, False)
        owner = os.fstat(parent)
        if not stat.S_ISDIR(owner.st_mode) or stat.S_IMODE(owner.st_mode) != 0o700 or owner.st_uid != os.geteuid():
            _refuse("private parent must belong to supervisor UID with mode 0700", "supervisor_domain_unavailable")
        _xattrs(parent, budget)
        parent_mount = _mount_id(parent, budget)
        donor = os.dup(donor_fd)
        os.set_inheritable(donor, False)
        _mode(os.fstat(donor), "directory")
        budget.check()
        # No retry/adoption on collision. The name is not a digest-cache lookup.
        candidate = "capture-" + secrets.token_hex(16)
        os.mkdir(candidate, 0o700, dir_fd=parent)
        name = candidate
        root = _open_dir(parent, name, budget)
        identity = os.fstat(root)
        partial = OwnedAllocation(name, root, parent, identity.st_dev, identity.st_ino, parent_mount)
        if _mount_id(root, budget) != parent_mount:
            _refuse("new capture crosses private mount")
        observed: list[InventoryEntry] = []
        entries = {entry.path: entry for entry in checked.inventory.entries}
        _walk(donor, root, "", entries, _mount_id(donor, budget), budget, [0], observed)
        if len(observed) != len(entries):
            _refuse("missing donor entry", "capture_integrity_failed")
        _verify_tree(root, checked.inventory, budget, staging=True)
        children: dict[str, list[InventoryEntry]] = {}
        for entry in checked.inventory.entries:
            children.setdefault(entry.path.rpartition("/")[0], []).append(entry)
        _freeze(root, children, "", budget)
        _verify_tree(root, checked.inventory, budget, staging=False)
        budget.check()
        if (os.fstat(root).st_dev, os.fstat(root).st_ino) != (identity.st_dev, identity.st_ino):
            _refuse("retained capture identity changed", "capture_integrity_failed")
        return OwnedCapture(name, root, parent, identity.st_dev, identity.st_ino, parent_mount,
                            CaptureIdentity(checked.sha256, checked.inventory.sha256,
                                            identity.st_dev, identity.st_ino, parent_mount))
    except (OSError, ProfileRefused) as exc:
        if name is not None and partial is None:
            # Even an open/deadline failure after mkdir must leave an explicit
            # owned allocation record. No claim of frozen or readable contents.
            partial = OwnedAllocation(name, root, parent, -1, -1, -1)
        if partial is None:
            if root >= 0:
                os.close(root)
            if parent >= 0:
                os.close(parent)
        code = exc.code if isinstance(exc, ProfileRefused) else "capture_integrity_failed"
        raise CaptureFailed(code, str(exc), partial) from exc
    finally:
        if donor >= 0:
            os.close(donor)
