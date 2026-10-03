"""One owned capture-quarantine removal; unprovisioned source prerequisite.

No scheduler, successful-capture retirement or durable capability recovery.
Preparation is explicitly quiescent and may block in kernel I/O. Polling never
performs tree work. Trusted helper/domain exclusion remains a prerequisite.
"""
from __future__ import annotations

import array
import fcntl
import os
import re
import select
import signal
import socket
import stat
import struct
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any

if __package__:
    from . import native_capture as capture
    from . import native_closure_profile as profile_api
else:
    import _native_capture as capture
    import _native_closure_profile as profile_api

RemovalRefused = capture.CaptureRefused
_fail = capture._fail
_uint = capture._uint
_digest = capture._digest
_exact = capture._exact
_canonical = capture._canonical
_json = capture._json
_hash = capture._hash
_root = capture._root
_read_bounded = capture._read_bounded
_closed_helper_elf = capture._closed_helper_elf
OwnedProcess = capture.OwnedProcess
ProcessIdentity = capture.ProcessIdentity
NS = capture.NS
FRAME_MAX = 4096
TRAFFIC_MAX = 16384
MAX_ENTRIES = 16384
MAX_METADATA = 8 * 1024 * 1024
SCHEMA = "agentdecompile.native-removal-ipc.v1"
RUNTIME_SCHEMA = "agentdecompile.native-removal-helper-runtime.v1"
INTERPRETER = "usr/bin/python3.12"
ENTRY = "app/native_removal_entry.py"
CONTROLLER = "app/native_removal.py"
CAPTURE_MODULE = "app/native_capture.py"
PROFILE_MODULE = "app/native_closure_profile.py"
BINDING_DOCUMENT = ".native-removal/binding.json"
INVENTORY_DOCUMENT = ".native-removal/inventory.json"
ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
REASONS = capture.REASONS - {"capture_integrity_failed"}
FIELDS = {
    "CHALLENGE": "allocation_id root_identity parent_identity helper_runtime_sha256 attempt_deadline_ns",
    "HELLO": "helper_runtime_sha256",
    "READY": "allocation_id root_identity parent_identity",
    "BEGIN": "removal_deadline_ns deadline_ceiling_ns",
    "COMPLETE": "allocation_id root_identity parent_identity removed_entries root_unlinked",
    "ERROR": "reason detail",
}
CAPS = {"CHALLENGE": 2048, "HELLO": 1024, "READY": 2048, "BEGIN": 1024, "COMPLETE": 2048, "ERROR": 2048}


def _reason(exc: Exception) -> str:
    reason = getattr(exc, "reason", getattr(exc, "code", "cleanup_incomplete"))
    return reason if reason in REASONS else "cleanup_incomplete"


def _payload(kind: str, value: Any) -> dict:
    if kind not in FIELDS:
        _fail("unknown removal frame")
    value = _exact(value, FIELDS[kind])
    for key, item in value.items():
        if key.endswith("sha256"):
            _digest(item)
        elif key in ("root_identity", "parent_identity"):
            _root(item)
        elif key.endswith("_ns") or key == "removed_entries":
            _uint(item)
            if key == "removed_entries" and item > MAX_ENTRIES:
                _fail("removal count cap", "limit_exceeded")
        elif key == "allocation_id":
            if type(item) is not str or re.fullmatch("[0-9a-f]{32}", item) is None:
                _fail("allocation ID")
        elif key == "root_unlinked":
            if item is not True:
                _fail("root unlink required")
        elif key == "reason":
            if type(item) is not str or item not in REASONS:
                _fail("unknown removal reason")
        elif key == "detail":
            try:
                valid = type(item) is str and "\0" not in item and len(item.encode("utf-8", "strict")) <= 256
            except UnicodeError:
                valid = False
            if not valid:
                _fail("detail string cap")
    return value


def encode_frame(kind: str, nonce: str, seq: int, payload: dict) -> bytes:
    _digest(nonce)
    _uint(seq)
    _payload(kind, payload)
    raw = _canonical(dict(schema=SCHEMA, kind=kind, nonce=nonce, seq=seq, payload=payload))
    if len(raw) > CAPS[kind]:
        _fail("kind byte cap", "limit_exceeded")
    return raw


def decode_frame(raw: bytes, *, nonce: str | None, seq: int) -> dict:
    document = _exact(_json(raw), "schema kind nonce seq payload")
    if document["schema"] != SCHEMA or type(document["kind"]) is not str:
        _fail("frame schema/kind")
    _digest(document["nonce"])
    if nonce is not None and document["nonce"] != nonce:
        _fail("nonce mismatch")
    if _uint(document["seq"]) != seq:
        _fail("sequence mismatch")
    _payload(document["kind"], document["payload"])
    if len(raw) > CAPS[document["kind"]]:
        _fail("kind byte cap", "limit_exceeded")
    return document


def receive_frame(channel: socket.socket, *, peer: tuple[int, int, int], nonce: str | None,
                  seq: int) -> tuple[dict | None, int]:
    """One nonblocking datagram. Close every delivered right before refusal."""
    raw, ancillary, flags, _ = channel.recvmsg(FRAME_MAX + 1, socket.CMSG_SPACE(256 * 4), socket.MSG_CMSG_CLOEXEC)
    credentials = []
    invalid = False
    for level, kind, data in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            rights = array.array("i")
            rights.frombytes(data[:len(data) - len(data) % rights.itemsize])
            for fd in rights:
                os.close(fd)
            invalid = True
        elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS and len(data) == struct.calcsize("3i"):
            credentials.append(struct.unpack("3i", data))
        else:
            invalid = True
    if invalid or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
        _fail("unexpected/truncated ancillary data")
    # Stream termination is readiness, not a credential-bearing frame.
    if not raw and not ancillary:
        return None, 0
    if credentials != [peer]:
        _fail("kernel sender credentials mismatch")
    return decode_frame(raw, nonce=nonce, seq=seq), len(raw)



@dataclass
class RemovalRootView:
    parent_fd: int
    root_fd: int
    allocation_id: str
    parent_identity: dict
    root_identity: dict
    used: bool = False


@dataclass(frozen=True)
class RemovalSummary:
    removed_entries: int
    root_unlinked: bool = True


@dataclass(frozen=True)
class _Budget:
    deadline_ns: int

    def check(self) -> None:
        if time.monotonic_ns() >= self.deadline_ns:
            _fail("removal deadline expired", "deadline_exceeded")

    def call(self, function, *args, **kwargs):
        self.check()
        result = function(*args, **kwargs)
        try:
            self.check()
        except Exception:
            if function is os.open:
                os.close(result)
            raise
        return result

    @property
    def deadline(self) -> float:
        return self.deadline_ns / NS


def _identity(fd: int, budget: _Budget) -> dict:
    info = budget.call(os.fstat, fd)
    mount = profile_api._mount_id(fd, budget)
    budget.check()
    return dict(device=info.st_dev, inode=info.st_ino, mount_id=mount)


def _snapshot(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _security(parent: int, name: str | None, budget: _Budget) -> None:
    # Trusted procfs exposes the retained parent, never a user pathname. The
    # final component's xattrs are queried no-follow, including symlinks;
    # an O_PATH descriptor itself cannot portably serve flistxattr on Linux.
    if name is None:
        names = budget.call(os.listxattr, parent)
    else:
        names = budget.call(os.listxattr, f"/proc/self/fd/{parent}/{name}", follow_symlinks=False)
    if any(value.startswith("security.") for value in names):
        _fail("security xattr anomaly", "root_layout_unsupported")


def _directory(info) -> None:
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) not in (0o555, 0o700)):
        _fail("directory ownership/mode anomaly", "root_layout_unsupported")


def _guard_root(view: RemovalRootView, budget: _Budget) -> None:
    _root(view.parent_identity)
    _root(view.root_identity)
    if type(view.allocation_id) is not str or re.fullmatch("[0-9a-f]{32}", view.allocation_id) is None:
        _fail("internal allocation ID")
    for fd in (view.parent_fd, view.root_fd):
        if type(fd) is not int or fd < 0:
            _fail("missing original anchor", "cleanup_incomplete")
        if budget.call(fcntl.fcntl, fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
            _fail("read-only directory anchor required", "root_layout_unsupported")
    parent = budget.call(os.fstat, view.parent_fd)
    root = budget.call(os.fstat, view.root_fd)
    _directory(root)
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
            or _identity(view.parent_fd, budget) != view.parent_identity
            or _identity(view.root_fd, budget) != view.root_identity
            or root.st_dev != parent.st_dev
            or view.root_identity["mount_id"] != view.parent_identity["mount_id"]):
        _fail("original anchor mismatch", "cleanup_incomplete")
    _security(view.parent_fd, None, budget)
    _security(view.root_fd, None, budget)
    anchor = budget.call(os.open, "capture-" + view.allocation_id,
                         os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=view.parent_fd)
    try:
        named = budget.call(os.fstat, anchor)
        if not stat.S_ISDIR(named.st_mode) or _identity(anchor, budget) != view.root_identity:
            _fail("root name association changed", "cleanup_incomplete")
    finally:
        os.close(anchor)
    budget.check()


class _Node:
    """Compact bounded plan; no nine-integer Python tuple retained per inode."""
    __slots__ = ("parts", "_packed", "mount_id", "children")

    def __init__(self, parts: tuple, snapshot: tuple, mount_id: int) -> None:
        self.parts = parts
        self.snapshot = snapshot
        self.mount_id = mount_id
        self.children = [] if stat.S_ISDIR(snapshot[2]) else ()

    @property
    def snapshot(self) -> tuple:
        return struct.unpack("<QQQQQQQqq", self._packed)

    @snapshot.setter
    def snapshot(self, value: tuple) -> None:
        self._packed = struct.pack("<QQQQQQQqq", *value)

    def retained_size(self) -> int:
        # Include conservative per-child list capacity plus simultaneous scan
        # name-list pointers; ancestor strings are shared with existing nodes.
        return (sys.getsizeof(self) + sys.getsizeof(self._packed) + sys.getsizeof(self.parts)
                + sys.getsizeof(self.mount_id) + sys.getsizeof(self.children) + 32
                + (sys.getsizeof(self.parts[-1]) if self.parts else 0))


def _pin(parent: int, name: str, view: RemovalRootView, budget: _Budget) -> tuple[int, tuple, int]:
    before = budget.call(os.stat, name, dir_fd=parent, follow_symlinks=False)
    anchor = budget.call(os.open, name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        info = budget.call(os.fstat, anchor)
        mount = profile_api._mount_id(anchor, budget)
        if (_snapshot(before) != _snapshot(info) or info.st_dev != view.root_identity["device"]
                or mount != view.root_identity["mount_id"] or info.st_uid != os.geteuid()
                or info.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX)):
            _fail("entry identity/ownership/mount anomaly", "root_layout_unsupported")
        if stat.S_ISDIR(info.st_mode):
            _directory(info)
        elif stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1 or not 0 <= info.st_size <= profile_api.MAX_FILE_BYTES:
                _fail("regular file link/size anomaly", "root_layout_unsupported")
        elif stat.S_ISLNK(info.st_mode):
            if info.st_nlink != 1:
                _fail("symlink hardlink anomaly", "root_layout_unsupported")
        else:
            _fail("special entry refused", "root_layout_unsupported")
        _security(parent, name, budget)
        if _snapshot(budget.call(os.stat, name, dir_fd=parent, follow_symlinks=False)) != _snapshot(info):
            _fail("entry changed while pinning", "cleanup_incomplete")
        return anchor, _snapshot(info), mount
    except Exception:
        os.close(anchor)
        raise


def _enumerate(fd: int, parts: tuple, budget: _Budget, counters: list[int]) -> list[str]:
    names = []
    budget.check()
    with os.scandir(fd) as scan:
        budget.check()
        for item in scan:
            budget.check()
            if counters[0] >= MAX_ENTRIES:
                _fail("descendant count cap", "limit_exceeded")
            path = "/".join((*parts, item.name))
            profile_api._path(path)
            cost = 384 + len(path.encode("utf-8")) * 4
            if counters[1] + cost > MAX_METADATA:
                _fail("retained metadata cap", "limit_exceeded")
            counters[0] += 1
            counters[1] += cost
            names.append(item.name)
    budget.check()
    return sorted(names, key=lambda name: name.encode("utf-8"))


def _open_pinned_directory(anchor: int, snapshot: tuple, budget: _Budget) -> int:
    # '.' is relative to the already pinned directory, not its replaceable name.
    fd = budget.call(os.open, ".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=anchor)
    try:
        if _snapshot(budget.call(os.fstat, fd)) != snapshot:
            _fail("directory changed during open", "cleanup_incomplete")
        return fd
    except Exception:
        os.close(fd)
        raise


def remove_owned_tree(view: RemovalRootView, *, deadline_ns: int) -> RemovalSummary:
    """Fixed child only: two metadata passes, guarded leaf deletion, no content IO.

    Python objects are trusted local provenance, not hostile in-process security.
    The parent owns writer retirement; this view is inherited only after BEGIN.
    """
    if type(view) is not RemovalRootView or view.used:
        _fail("removal view already consumed", "cleanup_incomplete")
    view.used = True
    now = time.monotonic_ns()
    budget = _Budget(min(_uint(deadline_ns), now + 20 * NS))
    _guard_root(view, budget)
    root = _Node((), _snapshot(budget.call(os.fstat, view.root_fd)), view.root_identity["mount_id"])
    totals = [0, 384, 0]

    def scan(fd: int, node: _Node, compare: bool) -> None:
        before = _snapshot(budget.call(os.fstat, fd))
        if before != node.snapshot:
            _fail("directory changed before walk", "cleanup_incomplete")
        counters = second_totals if compare else totals
        names = _enumerate(fd, node.parts, budget, counters)
        if compare and names != [child.parts[-1] for child in node.children]:
            _fail("second pass entry set changed", "cleanup_incomplete")
        for index, name in enumerate(names):
            anchor, snapshot, mount = _pin(fd, name, view, budget)
            child_fd = -1
            try:
                if compare:
                    child = node.children[index]
                    if snapshot != child.snapshot or mount != child.mount_id:
                        _fail("second pass metadata changed", "cleanup_incomplete")
                else:
                    child = _Node((*node.parts, name), snapshot, mount)
                    reserved = 384 + len("/".join(child.parts).encode("utf-8")) * 4
                    extra = max(0, child.retained_size() - reserved)
                    if totals[1] + extra > MAX_METADATA:
                        _fail("retained plan memory cap", "limit_exceeded")
                    totals[1] += extra
                    node.children.append(child)
                    if stat.S_ISREG(snapshot[2]):
                        totals[2] += snapshot[6]
                        if totals[2] > profile_api.MAX_TOTAL_BYTES:
                            _fail("aggregate file size cap", "limit_exceeded")
                if stat.S_ISDIR(snapshot[2]):
                    child_fd = _open_pinned_directory(anchor, snapshot, budget)
                    scan(child_fd, child, compare)
            finally:
                if child_fd >= 0:
                    os.close(child_fd)
                os.close(anchor)
            budget.check()
        if _snapshot(budget.call(os.fstat, fd)) != before:
            _fail("directory changed during enumeration", "cleanup_incomplete")

    scan(view.root_fd, root, False)
    second_totals = [0, 384, 0]
    _guard_root(view, budget)
    scan(view.root_fd, root, True)
    removed = 0
    chain = [(view.root_fd, root)]

    def guard() -> None:
        _guard_root(view, budget)
        for index, (fd, node) in enumerate(chain):
            if (_snapshot(budget.call(os.fstat, fd)) != node.snapshot
                    or profile_api._mount_id(fd, budget) != node.mount_id):
                _fail("retained ancestor changed", "cleanup_incomplete")
            if index:
                anchor, snapshot, mount = _pin(chain[index - 1][0], node.parts[-1], view, budget)
                try:
                    if snapshot != node.snapshot or mount != node.mount_id:
                        _fail("ancestor name changed", "cleanup_incomplete")
                finally:
                    os.close(anchor)
        budget.check()

    def refresh(fd: int, node: _Node, *, chmod: bool = False, directory_removed: bool = False) -> None:
        after = _snapshot(budget.call(os.fstat, fd))
        before = node.snapshot
        # Only mode/ctime for chmod, and directory size/time/nlink after removing
        # one child may change. Never overwrite unexplained owner/type/inode.
        expected_links = before[3] - int(directory_removed)
        if (after[:2] != before[:2] or after[4:6] != before[4:6]
                or after[3] != expected_links
                or after[2] != ((before[2] & ~0o777) | 0o700 if chmod else before[2])
                or (chmod and (after[6] != before[6] or after[7] != before[7]))):
            _fail("unexplained metadata after local mutation", "cleanup_incomplete")
        node.snapshot = after

    def empty(fd: int) -> None:
        budget.check()
        with os.scandir(fd) as scan:
            budget.check()
            if next(scan, None) is not None:
                _fail("directory not empty", "cleanup_incomplete")
        budget.check()

    def delete(fd: int, node: _Node) -> None:
        nonlocal removed
        guard()
        if stat.S_IMODE(node.snapshot[2]) == 0o555:
            budget.call(os.fchmod, fd, 0o700)
            refresh(fd, node, chmod=True)
        for child in node.children:
            name = child.parts[-1]
            guard()
            anchor, snapshot, mount = _pin(fd, name, view, budget)
            child_fd = -1
            try:
                if snapshot != child.snapshot or mount != child.mount_id:
                    _fail("entry changed before deletion", "cleanup_incomplete")
                directory = stat.S_ISDIR(snapshot[2])
                if directory:
                    child_fd = _open_pinned_directory(anchor, snapshot, budget)
                    chain.append((child_fd, child))
                    delete(child_fd, child)
                    guard()
                    chain.pop()
                guard()
                last, current, current_mount = _pin(fd, name, view, budget)
                try:
                    if current != child.snapshot or current_mount != child.mount_id:
                        _fail("named entry changed before syscall", "cleanup_incomplete")
                    budget.call(os.rmdir if directory else os.unlink, name, dir_fd=fd)
                finally:
                    os.close(last)
                refresh(fd, node, directory_removed=directory)
                removed += 1
            finally:
                if child_fd >= 0:
                    os.close(child_fd)
                os.close(anchor)
            budget.check()
        empty(fd)

    delete(view.root_fd, root)
    guard()
    budget.call(os.rmdir, "capture-" + view.allocation_id, dir_fd=view.parent_fd)
    # No name-present guard after our successful rmdir. ENOENT now is one
    # conjunct of our own syscall/postcondition proof, never retry authority.
    budget.check()
    try:
        os.stat("capture-" + view.allocation_id, dir_fd=view.parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        _fail("root name reappeared", "cleanup_incomplete")
    budget.check()
    detached = budget.call(os.fstat, view.root_fd)
    if (_identity(view.root_fd, budget) != view.root_identity or not stat.S_ISDIR(detached.st_mode)
            or detached.st_nlink != 0 or _identity(view.parent_fd, budget) != view.parent_identity
            or removed != totals[0]):
        _fail("root detach postcondition unavailable", "cleanup_incomplete")
    budget.check()
    return RemovalSummary(removed)

@dataclass(frozen=True)
class RemovalRuntimeBinding:
    schema: str
    runtime_inventory_sha256: str
    interpreter_sha256: str
    entry_sha256: str
    removal_module_sha256: str
    capture_module_sha256: str
    profile_module_sha256: str
    environment_sha256: str

    def canonical_bytes(self) -> bytes:
        if self.schema != RUNTIME_SCHEMA:
            _fail("removal binding schema", "runtime_dependency_unavailable")
        for key, value in self.__dict__.items():
            if key != "schema":
                _digest(value)
        if self.environment_sha256 != _hash(_canonical(ENVIRONMENT)):
            _fail("helper environment pin", "profile_pin_mismatch")
        return _canonical(dict(self.__dict__))


@dataclass(frozen=True)
class RemovalOwnerInputs:
    installation_fd: int
    installation_path: str
    helper_binding: RemovalRuntimeBinding
    helper_inventory_bytes: bytes
    dedicated_supervisor_domain: bool
    quiescent: bool


@dataclass(frozen=True)
class RemovalTiming:
    mode: str
    attempt_id: str
    deadline_ceiling_ns: int
    original_job_deadline_ns: int | None
    permit: MaintenancePermit | None = None


@dataclass(eq=False)
class RemovalClaim:
    quarantine: capture.CaptureQuarantine
    generation: int
    timing: RemovalTiming
    attempt_deadline_ns: int
    process: OwnedProcess | None = None
    spawn_attempted: bool = False
    state: str = "preparing"
    reason: str | None = None
    retired: bool = False
    prepared: PreparedRemoval | None = None
    held_fds: list[int] = field(default_factory=list)
    cancel_at_ns: int | None = None
    kill_at_ns: int | None = None
    qualified: object | None = None
    process_anchor: tuple = field(default=(), init=False, repr=False)


def _record_process(claim: RemovalClaim) -> None:
    """Retain the exact bound direct child before accepting any helper frame."""
    _check(claim)
    process = claim.process
    if claim.process_anchor or process is None or process.identity is None or process.pidfd < 0:
        _fail("remover process provenance unavailable", "owned_process_identity_unavailable")
    claim.process_anchor = (process, process.pid, process.pidfd, process.identity)


@dataclass(eq=False)
class RemovalDebtHolder:
    """One boot-local lane owner. No callbacks, IO, persistence or driver."""
    lane: capture.CaptureLane
    quiescent: bool = True
    entry: capture.CaptureQuarantine | None = field(default=None, init=False)
    permit: MaintenancePermit | None = field(default=None, init=False)


@dataclass(eq=False)
class MaintenancePermit:
    quarantine: capture.CaptureQuarantine
    generation: int
    recipient: RemovalDebtHolder
    consumed: bool = field(default=False, init=False)


def _check(claim: RemovalClaim) -> None:
    if type(claim) is not RemovalClaim or claim.retired:
        _fail("retired/unknown claim", "cleanup_incomplete")
    capture._check_removal_claim(claim.quarantine, claim, claim.generation)
    owner = claim.quarantine._removal_owner
    if owner is not None and (type(owner) is not RemovalDebtHolder or owner.entry is not claim.quarantine):
        _fail("maintenance owner no longer retains debt", "cleanup_incomplete")
    if claim.process_anchor:
        original, pid, pidfd, identity = claim.process_anchor
        if (claim.process is not original or original.pid != pid or original.pidfd != pidfd
                or original.identity is not identity):
            _fail("remover process identity replaced", "owned_process_identity_unavailable")


def _exited(claim: RemovalClaim) -> bool:
    process = claim.process
    if not claim.spawn_attempted:
        return process is None
    return (process is not None and process.identity is not None and not process.identity_lost
            and process.pidfd >= 0 and process.confirmed_exit and process.pid == process.identity.pid
            and bool(claim.process_anchor) and claim.process_anchor[0] is process
            and claim.process_anchor[1:3] == (process.pid, process.pidfd)
            and claim.process_anchor[3] is process.identity)


def transfer_removal_debt(quarantine: capture.CaptureQuarantine, expected_claim: RemovalClaim | None,
                          recipient: RemovalDebtHolder) -> MaintenancePermit:
    """Qualified indivisible local acknowledgment; pending IO cannot rearm."""
    capture._removal_authority(quarantine)
    generation = quarantine.removal_generation
    if (type(recipient) is not RemovalDebtHolder or recipient.lane is not quarantine.lane
            or recipient.quiescent is not True or threading.active_count() != 1
            or (recipient.entry is not None and recipient.entry is not quarantine)
            or generation == capture.UINT_MAX or len(quarantine._removal_history) >= 64):
        _fail("debt acknowledgment unavailable", "cleanup_incomplete")
    if expected_claim is None:
        if (generation != 0 or quarantine._removal_claim is not None or quarantine._removal_started
                or quarantine._removal_history or quarantine._removal_owner is not None):
            _fail("not original unclaimed generation zero", "cleanup_incomplete")
    else:
        _check(expected_claim)
        if (expected_claim.quarantine is not quarantine or expected_claim.reason is None
                or expected_claim.state not in ("cleanup_incomplete", "quarantined", "quarantined_pending_io")
                or not _exited(expected_claim) or expected_claim.qualified is not None):
            _fail("failed remover retirement unqualified", "cleanup_incomplete")
    for old in quarantine._removal_history:
        if type(old) is RemovalClaim and not _exited(old):
            _fail("earlier remover exit unqualified", "cleanup_incomplete")
    previous_owner = quarantine._removal_owner
    if previous_owner is not None and (type(previous_owner) is not RemovalDebtHolder
                                        or previous_owner.entry is not quarantine):
        _fail("previous debt owner changed", "cleanup_incomplete")
    if recipient.permit is not None and not recipient.permit.consumed:
        _fail("recipient has unused maintenance permit", "cleanup_incomplete")
    permit = MaintenancePermit(quarantine, generation + 1, recipient)
    history = [*quarantine._removal_history, expected_claim]
    # All validation/allocation precedes acknowledgment. Exact built-in holder
    # fields only below: no external IO/callback can interrupt the transition.
    recipient.entry = quarantine
    recipient.permit = permit
    if expected_claim is not None:
        expected_claim.retired = True
    quarantine._removal_history = history
    quarantine.removal_generation = generation + 1
    quarantine._removal_claim = None
    quarantine._removal_owner = recipient
    quarantine._removal_started = True
    quarantine.cleanup_state = "queued_owned_removal"
    if previous_owner is not None and previous_owner is not recipient:
        previous_owner.entry = None
        previous_owner.permit = None
    return permit


def _claim(quarantine: capture.CaptureQuarantine, timing: RemovalTiming, now_ns: int) -> RemovalClaim:
    provenance = capture._removal_authority(quarantine)
    if quarantine._removal_claim is not None or type(timing) is not RemovalTiming:
        _fail("quarantine already claimed", "cleanup_incomplete")
    _uint(now_ns)
    ceiling = _uint(timing.deadline_ceiling_ns)
    if timing.original_job_deadline_ns is not None:
        _uint(timing.original_job_deadline_ns)
    if (type(timing.attempt_id) is not str or re.fullmatch("[0-9a-f]{32}", timing.attempt_id) is None
            or timing.original_job_deadline_ns != provenance.original_job_deadline_ns):
        _fail("timing provenance mismatch", "deadline_exceeded")
    for old in quarantine._removal_history:
        if type(old) is RemovalClaim:
            if not _exited(old):
                _fail("prior remover retirement changed", "owned_process_identity_unavailable")
            if old.timing.attempt_id == timing.attempt_id:
                _fail("attempt identity reused", "ipc_binding_invalid")
    if timing.mode == "job":
        if (timing.permit is not None or provenance.original_job_deadline_ns is None
                or ceiling != provenance.original_job_deadline_ns or quarantine.removal_generation != 0
                or quarantine._removal_started or quarantine._removal_owner is not None):
            _fail("job ceiling/generation mismatch", "deadline_exceeded")
    elif timing.mode == "maintenance":
        permit = timing.permit
        if (type(permit) is not MaintenancePermit or permit.consumed or permit.quarantine is not quarantine
                or permit.generation != quarantine.removal_generation
                or permit.recipient is not quarantine._removal_owner
                or permit.recipient.entry is not quarantine or permit.recipient.permit is not permit
                or ceiling > now_ns + 20 * NS):
            _fail("maintenance permit unavailable", "cleanup_incomplete")
    else:
        _fail("unknown timing mode", "deadline_exceeded")
    claim = RemovalClaim(quarantine, quarantine.removal_generation, timing, min(now_ns + 20 * NS, ceiling))
    if timing.mode == "maintenance":
        timing.permit.consumed = True
    quarantine._removal_claim = claim
    quarantine._removal_started = True
    quarantine.cleanup_state = "queued_owned_removal"
    return claim


@dataclass
class PreparedRemoval:
    claim: RemovalClaim
    owner: RemovalOwnerInputs
    nonce: str
    runtime_sha256: str
    process: OwnedProcess
    channel: socket.socket
    stdout_fd: int
    stderr_fd: int
    prepared_at_ns: int = 0
    used: bool = False
    rx_seq: int = 0
    rx_bytes: int = 0
    tx_bytes: int = 0
    log_bytes: list[int] = field(default_factory=lambda: [0, 0])
    eof: list[bool] = field(default_factory=lambda: [False, False, False])

    def expected_ready(self) -> dict:
        a = self.claim.quarantine.allocation
        return dict(allocation_id=a.allocation_name.removeprefix("capture-"),
                    root_identity=dict(device=a.device, inode=a.inode, mount_id=a.mount_id),
                    parent_identity=dict(zip(("device", "inode", "mount_id"), a.parent_identity)))


@dataclass(frozen=True)
class RemovalPreparationFailure:
    reason: str
    quarantine: capture.CaptureQuarantine
    claim: RemovalClaim


@dataclass(frozen=True)
class RemovalPhaseUpdate:
    state: str
    reason: str | None = None
    kill_action: str | None = None

    def to_record(self) -> dict:
        record = {"state": self.state}
        if self.reason is not None:
            record["reason"] = self.reason
        if self.kill_action is not None:
            record["kill_action"] = self.kill_action
        return record


def _verify_installation(owner: RemovalOwnerInputs, budget: profile_api._Budget) -> str:
    """Authenticate full owner-pinned executable/import universe, not host PATH.

    The two metadata files are pinned separately and excluded from the runtime
    inventory to avoid a self-hash cycle. They are never import search locations.
    """
    binding = owner.helper_binding
    binding_raw = binding.canonical_bytes()
    root_path = owner.installation_path
    if (not os.path.isabs(root_path) or os.path.normpath(root_path) != root_path or root_path == "/"):
        _fail("immutable installation root required", "runtime_dependency_unavailable")
    root_stat = os.fstat(owner.installation_fd)
    path_stat = os.stat(root_path, follow_symlinks=False)
    if ((root_stat.st_dev, root_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino)
            or not stat.S_ISDIR(root_stat.st_mode)
            or not os.fstatvfs(owner.installation_fd).f_flag & os.ST_RDONLY):
        _fail("installation must be retained read-only mount", "runtime_dependency_unavailable")
    inventory = profile_api.validate_inventory(owner.helper_inventory_bytes,
                                              expected_sha256=binding.runtime_inventory_sha256)
    entries = {e.path: e for e in inventory.entries}
    for path, digest in ((INTERPRETER, binding.interpreter_sha256), (ENTRY, binding.entry_sha256),
                         (CONTROLLER, binding.removal_module_sha256), (CAPTURE_MODULE, binding.capture_module_sha256),
                         (PROFILE_MODULE, binding.profile_module_sha256)):
        entry = entries.get(path)
        if (entry is None or entry.type != "file" or entry.sha256 != digest
                or entry.permission_class != ("executable" if path == INTERPRETER else "data")):
            _fail("independent helper role pin mismatch", "profile_pin_mismatch")
    for path in ("usr/lib/python3.12", "usr/lib/python3.12/lib-dynload"):
        if path not in entries or entries[path].type != "directory":
            _fail("immutable stdlib closure missing", "runtime_dependency_unavailable")
    for landmark in ("usr/lib/python3.12/os.py", "usr/lib/python3.12/encodings/__init__.py"):
        if landmark not in entries or entries[landmark].type != "file":
            _fail("relocated CPython startup landmarks missing", "runtime_dependency_unavailable")
    if any(path.endswith((".zip", ".pyc", ".pyo", ".pth")) or path.rsplit("/", 1)[-1] in
           ("pybuilddir.txt", "pyvenv.cfg") for path in entries):
        _fail("helper alternate startup/import source forbidden", "runtime_dependency_unavailable")
    # Verify all inventory entries using the reviewed no-follow copier reader.
    # Metadata lives beside the immutable import universe, excluded explicitly.
    mount = profile_api._mount_id(owner.installation_fd, budget)
    def walk(fd: int, prefix: str, seen: list[str]) -> None:
        for name in profile_api._names(fd, prefix, budget, [len(seen)]):
            path = prefix + name
            if path == ".native-removal":
                continue
            entry = entries.get(path)
            if entry is None:
                _fail("extra immutable installation entry", "runtime_dependency_unavailable")
            if entry.type == "directory":
                child = profile_api._open_dir(fd, name, budget)
                try:
                    if profile_api._mount_id(child, budget) != mount:
                        _fail("installation mount crossing", "runtime_dependency_unavailable")
                    walk(child, path + "/", seen)
                finally:
                    os.close(child)
            elif entry.type == "file":
                profile_api._file(fd, name, entry, mount, budget, None)
                _closed_helper_elf(fd, name, entry, budget, interpreter=path == INTERPRETER)
            else:
                # Fixed installation refuses aliases; no host-dependent loader
                # paths can escape via a provisioned symlink.
                _fail("helper installation symlink unsupported", "runtime_dependency_unavailable")
            seen.append(path)
    seen: list[str] = []
    walk(owner.installation_fd, "", seen)
    if set(seen) != set(entries):
        _fail("incomplete helper inventory", "runtime_dependency_unavailable")
    metadata = profile_api._open_dir(owner.installation_fd, ".native-removal", budget)
    try:
        if profile_api._mount_id(metadata, budget) != mount or set(profile_api._names(metadata, "", budget, [0])) != {"binding.json", "inventory.json"}:
            _fail("helper metadata layout", "runtime_dependency_unavailable")
        for name, expected in (("binding.json", binding_raw), ("inventory.json", owner.helper_inventory_bytes)):
            raw = _read_bounded(f"/proc/self/fd/{metadata}/{name}", len(expected), budget)
            if raw != expected:
                _fail("immutable helper metadata pin mismatch", "profile_pin_mismatch")
    finally:
        os.close(metadata)
    return _hash(binding_raw)


def _bind_process(process: OwnedProcess, owner: RemovalOwnerInputs, runtime_sha: str,
                  budget: profile_api._Budget) -> None:
    """Direct child remains unreaped until pidfd and actual identity are bound."""
    process.pidfd = os.pidfd_open(process.pid, 0)
    os.set_inheritable(process.pidfd, False)
    expected_exe = owner.installation_path + "/" + INTERPRETER
    expected_argv = (expected_exe, "-I", "-S", "-B", owner.installation_path + "/" + ENTRY)
    aggregate = 0
    def read(name: str) -> bytes:
        nonlocal aggregate
        raw = _read_bounded(f"/proc/{process.pid}/{name}", 65536, budget)
        aggregate += len(raw)
        if aggregate > 512 * 1024:
            _fail("process identity aggregate cap", "limit_exceeded")
        return raw
    first = read("stat")
    fields = first[first.rfind(b")") + 2:].split()
    status = dict(line.split(b":", 1) for line in read("status").splitlines() if b":" in line)
    argv = tuple(v.decode("utf-8", "strict") for v in read("cmdline").rstrip(b"\0").split(b"\0"))
    executable = os.readlink(f"/proc/{process.pid}/exe")
    second = read("stat")
    again = second[second.rfind(b")") + 2:].split()
    uid, gid = os.geteuid(), os.getegid()
    if (len(fields) < 20 or len(again) < 20 or fields[19] != again[19]
            or int(fields[1]) != os.getpid() or int(again[1]) != os.getpid()
            or status.get(b"Uid", b"").split() != [str(uid).encode()] * 4
            or status.get(b"Gid", b"").split() != [str(gid).encode()] * 4
            or argv != expected_argv or executable != expected_exe):
        _fail("owned child process association unavailable", "owned_process_identity_unavailable")
    process.identity = ProcessIdentity(process.pid, int(fields[19]), uid, gid, os.getpid(), executable, argv, runtime_sha)


def _spawn_fixed(owner: RemovalOwnerInputs, descriptors: list[int]) -> int:
    """Single-threaded posix_spawn; collision-safe dup2 and explicit close set.

    No Python preexec callback. All original foreign FDs close before exec;
    nothing except 0..5 is inherited by the fixed interpreter.
    """
    safe: list[int] = []
    try:
        for fd in descriptors:
            safe.append(fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 128))
        actions = [(os.POSIX_SPAWN_DUP2, fd, target) for target, fd in enumerate(safe)]
        # Quiescent/single-threaded prerequisite makes this snapshot stable.
        open_fds = []
        with os.scandir("/proc/self/fd") as scan:
            for item in scan:
                if item.name.isdigit():
                    fd = int(item.name)
                    if fd > 5:
                        open_fds.append(fd)
        for fd in open_fds:
            try:
                fcntl.fcntl(fd, fcntl.F_GETFD)
            except OSError:
                continue  # closed scandir handle
            actions.append((os.POSIX_SPAWN_CLOSE, fd))
        executable = owner.installation_path + "/" + INTERPRETER
        argv = [executable, "-I", "-S", "-B", owner.installation_path + "/" + ENTRY]
        # Entry changes cwd before any application imports. Spawn cannot portably
        # chdir without Python preexec; the parent's quiescent cwd change is
        # restored even on failure, with the old directory retained as a handle.
        cwd = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fchdir(owner.installation_fd)
            return os.posix_spawn(executable, argv, ENVIRONMENT, file_actions=actions,
                                  setsigmask=(), setsigdef=(signal.SIGTERM, signal.SIGINT, signal.SIGPIPE))
        finally:
            os.fchdir(cwd)
            os.close(cwd)
    finally:
        for fd in safe:
            os.close(fd)



def _view(quarantine: capture.CaptureQuarantine) -> RemovalRootView:
    a = quarantine.allocation
    return RemovalRootView(a.parent_fd, a.root_fd, a.allocation_name.removeprefix("capture-"),
                           dict(zip(("device", "inode", "mount_id"), a.parent_identity)),
                           dict(device=a.device, inode=a.inode, mount_id=a.mount_id))


def _send(prepared: PreparedRemoval, kind: str, seq: int, payload: dict) -> None:
    _check(prepared.claim)
    raw = encode_frame(kind, prepared.nonce, seq, payload)
    if prepared.tx_bytes + len(raw) > TRAFFIC_MAX:
        _fail("send traffic cap", "limit_exceeded")
    if prepared.channel.send(raw, socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL) != len(raw):
        _fail("unknown control send disposition")
    prepared.tx_bytes += len(raw)


def _receive(prepared: PreparedRemoval) -> dict | None:
    _check(prepared.claim)
    identity = prepared.process.identity
    if identity is None or prepared.process.identity_lost or prepared.claim.process is not prepared.process:
        _fail("lost remover association", "owned_process_identity_unavailable")
    frame, count = receive_frame(prepared.channel, peer=(identity.pid, identity.uid, identity.gid),
                                 nonce=prepared.nonce, seq=prepared.rx_seq)
    prepared.rx_bytes += count
    if prepared.rx_bytes > TRAFFIC_MAX:
        _fail("receive traffic cap", "limit_exceeded")
    if frame is not None:
        prepared.rx_seq += 1
    return frame


def _drain_log(prepared: PreparedRemoval, index: int, cap: int) -> int:
    _check(prepared.claim)
    raw = os.read(prepared.stdout_fd if index == 0 else prepared.stderr_fd, cap)
    prepared.log_bytes[index] += len(raw)
    if prepared.log_bytes[index] > 1024 * 1024 or sum(prepared.log_bytes) > 2 * 1024 * 1024:
        _fail("diagnostic byte cap", "limit_exceeded")
    if not raw:
        prepared.eof[index + 1] = True
    return len(raw)


def prepare_removal(quarantine: capture.CaptureQuarantine, owner_inputs: RemovalOwnerInputs,
                    timing: RemovalTiming) -> PreparedRemoval | RemovalPreparationFailure:
    """Quiescent maintenance only; originals/lane never leave quarantine."""
    entered = time.monotonic_ns()
    claim = _claim(quarantine, timing, entered)
    owner = owner_inputs
    budget = _Budget(claim.attempt_deadline_ns)
    channels = []
    try:
        _check(claim)
        if (type(owner) is not RemovalOwnerInputs or owner.quiescent is not True
                or owner.dedicated_supervisor_domain is not True or threading.active_count() != 1
                or os.getuid() != os.geteuid() or os.getgid() != os.getegid()):
            _fail("explicit quiescent trusted domain required", "supervisor_domain_unavailable")
        budget.check()
        for name in ("pidfd_open", "P_PIDFD", "posix_spawn", "O_PATH"):
            if not hasattr(os, name):
                _fail("required process facility missing", "runtime_dependency_unavailable")
        if not hasattr(signal, "pidfd_send_signal"):
            _fail("pidfd signal unavailable", "runtime_dependency_unavailable")
        a = quarantine.allocation
        for fd in (a.parent_fd, a.root_fd):
            if os.get_inheritable(fd):
                _fail("original anchor is inheritable", "cleanup_incomplete")
            budget.check()
        _guard_root(_view(quarantine), budget)
        installation = os.dup(owner.installation_fd)
        claim.held_fds.append(installation)
        budget.check()
        os.set_inheritable(installation, False)
        owner = replace(owner, installation_fd=installation)
        runtime_sha = _verify_installation(owner, budget)
        budget.check()
        duplicates = []
        for original in (a.parent_fd, a.root_fd):
            budget.check()
            fd = os.dup(original)
            claim.held_fds.append(fd)
            budget.check()
            os.set_inheritable(fd, False)
            duplicates.append(fd)
        parent_channel, child_channel = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC)
        channels.extend((parent_channel, child_channel))
        for channel in channels:
            channel.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        budget.check()
        out_r, out_w = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        claim.held_fds.extend((out_r, out_w))
        err_r, err_w = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        claim.held_fds.extend((err_r, err_w))
        null = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        claim.held_fds.append(null)
        budget.check()
        _check(claim)
        claim.spawn_attempted = True
        claim.process = OwnedProcess(-1)
        claim.process.pid = _spawn_fixed(owner, [null, out_w, err_w, child_channel.fileno(), *duplicates])
        budget.check()
        _bind_process(claim.process, owner, runtime_sha, budget)
        _record_process(claim)
        budget.check()
        child_channel.close()
        channels.remove(child_channel)
        for fd in (out_w, err_w, null):
            os.close(fd)
            claim.held_fds.remove(fd)
        import secrets
        prepared = PreparedRemoval(claim, owner, secrets.token_hex(32), runtime_sha,
                                   claim.process, parent_channel, out_r, err_r)
        claim.prepared = prepared
        _send(prepared, "CHALLENGE", 0, dict(**prepared.expected_ready(), helper_runtime_sha256=runtime_sha,
                                            attempt_deadline_ns=claim.attempt_deadline_ns))
        while prepared.rx_seq < 2:
            _check(claim)
            budget.check()
            ready = select.select([parent_channel, out_r, err_r, claim.process.pidfd], [], [],
                                  min(0.05, max(0, (claim.attempt_deadline_ns - time.monotonic_ns()) / NS)))[0]
            budget.check()
            if claim.process.pidfd in ready:
                claim.process.observe_exit()
                _fail("remover exited before READY", "owned_process_identity_unavailable")
            for fd in (out_r, err_r):
                if fd in ready:
                    _drain_log(prepared, 0 if fd == out_r else 1, 4096)
            if parent_channel in ready:
                frame = _receive(prepared)
                if frame is None:
                    _fail("helper EOF before READY")
                if frame["kind"] == "ERROR":
                    _fail(frame["payload"]["detail"], frame["payload"]["reason"])
                if prepared.rx_seq == 1:
                    if frame["kind"] != "HELLO" or frame["payload"] != {"helper_runtime_sha256": runtime_sha}:
                        _fail("HELLO binding mismatch")
                elif frame["kind"] != "READY" or frame["payload"] != prepared.expected_ready():
                    _fail("READY binding mismatch")
        budget.check()
        prepared.prepared_at_ns = time.monotonic_ns()
        claim.state = "prepared"
        return prepared
    except Exception as exc:
        _check(claim)
        claim.reason = _reason(exc)
        claim.state = "cleanup_incomplete"
        quarantine.cleanup_state = "cleanup_incomplete"
        for channel in channels:
            channel.close()
        if claim.process is not None and claim.process.identity is not None:
            claim.process.send_signal(signal.SIGKILL)
            claim.kill_at_ns = time.monotonic_ns()
        return RemovalPreparationFailure(claim.reason, quarantine, claim)


@dataclass
class RemovalRun:
    prepared: PreparedRemoval
    state: str = "removing"
    reason: str | None = None
    complete: bool = False
    summary: RemovalSummary | None = None
    cancel_at_ns: int | None = None
    kill_at_ns: int | None = None
    term_until_ns: int | None = None
    exit_until_ns: int | None = None
    taken: bool = False

    def _current(self) -> RemovalClaim:
        claim = self.prepared.claim
        _check(claim)
        if claim.prepared is not self.prepared or self.prepared.process is not claim.process:
            _fail("prepared remover association changed", "cleanup_incomplete")
        return claim

    def request_cancel(self, now_ns: int, reason: str = "cancelled") -> None:
        claim = self._current()
        _uint(now_ns)
        if reason not in REASONS | {"cancelled"}:
            _fail("invalid local cancellation reason")
        if self.taken or self.reason is not None:
            return
        now_ns = max(now_ns, time.monotonic_ns())
        self.reason = claim.reason = reason
        self.complete = False
        self.summary = None
        claim.qualified = None
        self.cancel_at_ns = claim.cancel_at_ns = now_ns
        self.term_until_ns = min(now_ns + 5 * NS, claim.attempt_deadline_ns)
        self.exit_until_ns = min(self.term_until_ns + 5 * NS, claim.attempt_deadline_ns)
        self.state = claim.state = "terminating"
        claim.process.send_signal(signal.SIGTERM)

    def _advance_cancel(self, now_ns: int) -> None:
        claim = self._current()
        if self.reason is None:
            return
        if claim.process.confirmed_exit:
            self.state = claim.state = "quarantined"
            return
        if now_ns >= self.term_until_ns and self.kill_at_ns is None:
            claim.process.send_signal(signal.SIGKILL)
            self.kill_at_ns = claim.kill_at_ns = now_ns
            self.state = claim.state = "killing"
        if now_ns >= self.exit_until_ns:
            self.state = claim.state = "quarantined_pending_io"

    def poll(self, now_ns: int) -> RemovalPhaseUpdate:
        """At most16 events/64KiB/5ms, with no filesystem/proc-path work."""
        claim = self._current()
        _uint(now_ns)
        if self.taken:
            _fail("removal disposition transferred")
        start = time.monotonic_ns()
        now_ns = max(now_ns, start)
        prepared = self.prepared
        process = prepared.process
        if self.reason is None and (process.identity is None or process.identity_lost):
            self.request_cancel(now_ns, "owned_process_identity_unavailable")
        if self.reason is None and now_ns >= claim.attempt_deadline_ns:
            self.request_cancel(now_ns, "deadline_exceeded")
        bytes_left, events = 65536, 0
        while events < 16 and bytes_left > FRAME_MAX and time.monotonic_ns() - start < 5_000_000:
            sources = [prepared.channel] if not prepared.eof[0] else []
            sources += [fd for index, fd in enumerate((prepared.stdout_fd, prepared.stderr_fd)) if not prepared.eof[index + 1]]
            if process.pidfd >= 0 and not process.confirmed_exit and not process.identity_lost:
                sources.append(process.pidfd)
            try:
                ready = select.select(sources, [], [], 0)[0]
            except (OSError, ValueError):
                self.request_cancel(max(now_ns, time.monotonic_ns()), "owned_process_identity_unavailable")
                break
            if not ready:
                break
            for source in ready:
                if events >= 16 or bytes_left <= FRAME_MAX or time.monotonic_ns() - start >= 5_000_000:
                    break
                self._current()
                events += 1
                try:
                    if source is prepared.channel:
                        bytes_left -= FRAME_MAX + 1
                        frame = _receive(prepared)
                        if frame is None:
                            prepared.eof[0] = True
                            if not self.complete:
                                _fail("EOF without COMPLETE")
                        elif self.complete or self.reason is not None:
                            _fail("post-terminal frame")
                        elif frame["kind"] == "ERROR":
                            _fail(frame["payload"]["detail"], frame["payload"]["reason"])
                        elif frame["kind"] != "COMPLETE":
                            _fail("expected COMPLETE")
                        else:
                            value = frame["payload"]
                            if ({key: value[key] for key in prepared.expected_ready()} != prepared.expected_ready()
                                    or value["root_unlinked"] is not True or value["removed_entries"] > MAX_ENTRIES):
                                _fail("COMPLETE binding mismatch")
                            self.complete = True
                            self.summary = RemovalSummary(value["removed_entries"])
                            self.state = claim.state = "completion_pending_exit"
                    elif source == process.pidfd:
                        process.observe_exit()
                        if process.identity_lost:
                            _fail("owned reap association lost", "owned_process_identity_unavailable")
                    else:
                        # Reserve before reading: cumulative-cap refusal must
                        # still charge every byte successfully discarded.
                        diagnostic_cap = min(4096, bytes_left)
                        bytes_left -= diagnostic_cap
                        _drain_log(prepared, 0 if source == prepared.stdout_fd else 1, diagnostic_cap)
                except BlockingIOError:
                    pass
                except (OSError, RemovalRefused) as exc:
                    self.request_cancel(max(now_ns, time.monotonic_ns()), _reason(exc))
        end = max(now_ns, time.monotonic_ns())
        if self.reason is None and (process.identity is None or process.identity_lost):
            self.request_cancel(end, "owned_process_identity_unavailable")
        if self.reason is None and end >= claim.attempt_deadline_ns:
            self.request_cancel(end, "deadline_exceeded")
        if self.reason is None and process.confirmed_exit and process.exit_code != 0:
            self.request_cancel(end, "cleanup_incomplete")
        if self.reason is None and process.confirmed_exit and all(prepared.eof):
            if self.complete and process.exit_code == 0:
                self.state = claim.state = "removed"
                claim.qualified = _QualifiedCompletion(self, claim, claim.generation, process,
                                                        process.identity, end, self.summary)
            else:
                self.request_cancel(end, "ipc_binding_invalid")
        self._advance_cancel(end)
        if self.state == "quarantined_pending_io":
            return RemovalPhaseUpdate(self.state, self.reason, "kill-failed")
        if self.state == "quarantined":
            return RemovalPhaseUpdate(self.state, self.reason)
        return RemovalPhaseUpdate(self.state)

    def take_disposition(self) -> capture.CleanupDisposition:
        claim = self._current()
        if self.taken:
            _fail("removal disposition already consumed", "cleanup_incomplete")
        if self.reason is not None:
            if self.state not in ("quarantined", "quarantined_pending_io"):
                _fail("removal cancellation unfinished", "cleanup_incomplete")
            self.taken = True
            claim.quarantine.cleanup_state = "cleanup_incomplete"
            return capture.CleanupDisposition("cleanup_incomplete")
        proof = claim.qualified
        now = time.monotonic_ns()
        if (type(proof) is not _QualifiedCompletion or proof.run is not self or proof.claim is not claim
                or proof.generation != claim.generation or self.state != "removed" or not self.complete
                or self.summary is not proof.summary or proof.process is not claim.process
                or proof.identity is not claim.process.identity or not _exited(claim)
                or claim.process.exit_code != 0 or not all(self.prepared.eof)
                or now >= claim.attempt_deadline_ns or proof.qualified_at_ns >= claim.attempt_deadline_ns):
            self.request_cancel(now, "deadline_exceeded" if now >= claim.attempt_deadline_ns else "cleanup_incomplete")
            _fail("removal completion unqualified", "cleanup_incomplete")
        # Internal proof is rechecked here, then exchanged for a capture-owned
        # one-use terminal gate; no caller state string can release admission.
        terminal = capture._qualify_removal(claim.quarantine, claim, claim.generation, claim.process,
                                            claim.attempt_deadline_ns)
        for previous in claim.quarantine._removal_history:
            if type(previous) is RemovalClaim and not _exited(previous):
                _fail("prior remover retirement changed", "owned_process_identity_unavailable")
        result = capture._finalize_removal(claim.quarantine, claim, claim.generation, terminal)
        self.taken = True
        # The exact terminal tombstone authorizes disposal of this bounded
        # history too. Retired callers themselves still cannot release handles.
        for completed in [claim, *claim.quarantine._removal_history]:
            if type(completed) is not RemovalClaim:
                continue
            if completed.prepared is not None:
                completed.prepared.channel.close()
            for fd in completed.held_fds:
                os.close(fd)
            completed.held_fds.clear()
            if completed.process is not None and completed.process.pidfd >= 0:
                os.close(completed.process.pidfd)
                completed.process.pidfd = -1
        owner = claim.quarantine._removal_owner
        if owner is not None and owner.entry is claim.quarantine:
            owner.entry = None
            owner.permit = None
        return result


@dataclass(frozen=True)
class _QualifiedCompletion:
    run: RemovalRun
    claim: RemovalClaim
    generation: int
    process: OwnedProcess
    identity: ProcessIdentity
    qualified_at_ns: int
    summary: RemovalSummary


def begin_removal(prepared: PreparedRemoval) -> RemovalRun:
    claim = prepared.claim
    _check(claim)
    if prepared.used or claim.prepared is not prepared or claim.state != "prepared":
        _fail("prepared removal already consumed", "cleanup_incomplete")
    prepared.used = True
    run = RemovalRun(prepared)
    now = time.monotonic_ns()
    try:
        if now >= claim.attempt_deadline_ns:
            _fail("prepared removal expired", "deadline_exceeded")
        if (prepared.process is not claim.process or prepared.process.identity is None
                or prepared.process.identity_lost or prepared.process.confirmed_exit):
            _fail("prepared remover association unavailable", "owned_process_identity_unavailable")
        claim.state = "awaiting_begin_delivery"
        _send(prepared, "BEGIN", 1, dict(removal_deadline_ns=claim.attempt_deadline_ns,
                                       deadline_ceiling_ns=claim.timing.deadline_ceiling_ns))
        claim.state = "removing"
    except Exception as exc:
        run.request_cancel(now, _reason(exc))
    return run
