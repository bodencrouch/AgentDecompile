"""Fixed single-use capture supervisor; source prerequisite, not a sandbox.

Preparation is ONLY an explicit quiescent, single-threaded maintenance operation.
It may block in kernel filesystem/spawn calls. No scheduler registration exists.
The immutable installation and dedicated trusted UID are owner prerequisites.
Physical removal is deliberately a separate, still-required helper interface.
"""
from __future__ import annotations

import array
import fcntl
import hashlib
import json
import os
import re
import select
import signal
import socket
import stat
import struct
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Literal

# The clean entry loads these exact files under fixed private names, avoiding
# worker/__init__.py and its unrelated identity/store/registry imports.
if __package__:
    from . import native_closure_profile as profile_api
else:
    import _native_closure_profile as profile_api

SCHEMA = "agentdecompile.native-capture-ipc.v1"
RUNTIME_SCHEMA = "agentdecompile.native-capture-helper-runtime.v1"
ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
INTERPRETER = "usr/bin/python3.12"
ENTRY = "app/native_capture_entry.py"
CONTROLLER = "app/native_capture.py"
PROFILE_MODULE = "app/native_closure_profile.py"
BINDING_DOCUMENT = ".native-capture/binding.json"
INVENTORY_DOCUMENT = ".native-capture/inventory.json"
NS = 1_000_000_000
UINT_MAX = 2**64 - 1
FRAME_MAX = 4096
TRAFFIC_MAX = 16 * 1024
REASONS = frozenset(("profile_pin_mismatch", "supervisor_domain_unavailable", "capture_integrity_failed",
                     "root_layout_unsupported", "owned_process_identity_unavailable", "runtime_dependency_unavailable",
                     "limit_exceeded", "deadline_exceeded", "ipc_binding_invalid", "cleanup_incomplete"))
FIELDS = {
    "CHALLENGE": "profile_id profile_sha256 inventory_sha256 helper_runtime_sha256 allocation_id root_identity",
    "HELLO": "helper_runtime_sha256",
    "READY": "allocation_id root_identity profile_sha256 inventory_sha256",
    "BEGIN": "capture_deadline_ns absolute_deadline_ns",
    "COMPLETE": "allocation_id root_identity profile_sha256 inventory_sha256 entry_count total_file_bytes",
    "ERROR": "reason detail",
}
CAPS = {"CHALLENGE": 2048, "HELLO": 1024, "READY": 2048, "BEGIN": 1024, "COMPLETE": 2048, "ERROR": 2048}


class CaptureRefused(ValueError):
    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail[:256]
        super().__init__(f"{reason}: {self.detail}")


def _fail(detail: str, reason: str = "ipc_binding_invalid") -> None:
    raise CaptureRefused(reason, detail)


def _uint(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= UINT_MAX:
        _fail("expected UInt")
    return value


def _digest(value: Any) -> str:
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        _fail("expected digest")
    return value


def _exact(value: Any, fields: str) -> dict:
    if type(value) is not dict or set(value) != set(fields.split()):
        _fail("unknown/missing fields")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(raw: bytes, cap: int = FRAME_MAX) -> dict:
    if type(raw) is not bytes or len(raw) > cap:
        _fail("frame byte cap", "limit_exceeded")
    # Preflight allocation bounds, including punctuation only outside strings.
    depth = members = 0
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
            if depth > 4:
                _fail("frame depth", "limit_exceeded")
        elif byte in (125, 93):
            depth -= 1
        elif byte == 58:
            members += 1
            if members > 64:
                _fail("frame members", "limit_exceeded")

    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                _fail("duplicate key")
            result[key] = value
        return result

    def number(value: str) -> None:
        _fail("noninteger number")

    try:
        document = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
                              parse_float=number, parse_constant=number)
        if type(document) is not dict or _canonical(document) != raw:
            _fail("noncanonical JSON")
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        if isinstance(exc, CaptureRefused):
            raise
        raise CaptureRefused("ipc_binding_invalid", "invalid JSON") from exc
    return document


def _root(value: Any) -> dict:
    value = _exact(value, "device inode mount_id")
    for item in value.values():
        _uint(item)
    return value


def _payload(kind: str, value: Any) -> dict:
    if kind not in FIELDS:
        _fail("unknown frame kind")
    value = _exact(value, FIELDS[kind])
    for key, item in value.items():
        if key.endswith("sha256"):
            _digest(item)
        elif key == "root_identity":
            _root(item)
        elif key in ("entry_count", "total_file_bytes", "capture_deadline_ns", "absolute_deadline_ns"):
            _uint(item)
        elif key == "allocation_id":
            if type(item) is not str or re.fullmatch("[0-9a-f]{32}", item) is None:
                _fail("allocation ID")
        elif key == "profile_id":
            if item != profile_api.PROFILE_ID:
                _fail("profile family")
        elif key == "reason":
            if type(item) is not str or item not in REASONS:
                _fail("unknown reason")
        elif key == "detail":
            if type(item) is not str or "\0" in item or len(item.encode("utf-8")) > 256:
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


@dataclass(frozen=True)
class HelperRuntimeBinding:
    schema: str
    runtime_inventory_sha256: str
    interpreter_sha256: str
    entry_sha256: str
    capture_module_sha256: str
    profile_module_sha256: str
    environment_sha256: str

    def canonical_bytes(self) -> bytes:
        record = dict(self.__dict__)
        if self.schema != RUNTIME_SCHEMA:
            _fail("helper binding schema", "runtime_dependency_unavailable")
        for key, value in record.items():
            if key != "schema":
                _digest(value)
        if self.environment_sha256 != _hash(_canonical(ENVIRONMENT)):
            _fail("helper environment pin", "profile_pin_mismatch")
        return _canonical(record)


@dataclass(frozen=True)
class OwnerInputs:
    """Owner configuration, never constructed from a task manifest.

    installation_path is the provisioned immutable installation's absolute root;
    all launch paths are fixed relative to that anchored root. Inventory covers
    its complete executable/import closure, excluding only the two bounded
    read-only metadata documents in .native-capture (not on sys.path).
    """
    installation_fd: int
    installation_path: str
    private_parent_fd: int
    donor_fd: int
    profile_bytes: bytes
    inventory_bytes: bytes
    profile_sha256: str
    inventory_sha256: str
    entry_count: int
    total_file_bytes: int
    helper_binding: HelperRuntimeBinding
    helper_inventory_bytes: bytes
    dedicated_supervisor_domain: bool
    quiescent: bool
    lane: CaptureLane


@dataclass
class CaptureLane:
    """Retained owner latch. It is NOT serialized or released by closing FDs."""
    occupant: object | None = None


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start_ticks: int
    uid: int
    gid: int
    parent_pid: int
    executable: str
    argv: tuple[str, ...]
    runtime_sha256: str


@dataclass
class OwnedProcess:
    pid: int
    pidfd: int = -1
    identity: ProcessIdentity | None = None
    confirmed_exit: bool = False
    exit_code: int | None = None
    identity_lost: bool = False

    def observe_exit(self) -> None:
        if self.confirmed_exit or self.pidfd < 0 or self.identity is None or self.identity_lost:
            return
        try:
            if not select.select([self.pidfd], [], [], 0)[0]:
                return
            result = os.waitid(os.P_PIDFD, self.pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if result is None:
                return
            if result.si_pid != self.identity.pid:
                self.identity_lost = True
                return
            reaped = os.waitid(os.P_PIDFD, self.pidfd, os.WEXITED | os.WNOHANG)
            if reaped is None or reaped.si_pid != self.identity.pid or (reaped.si_code, reaped.si_status) != (result.si_code, result.si_status):
                self.identity_lost = True
                return
            self.exit_code = reaped.si_status if reaped.si_code == os.CLD_EXITED else -reaped.si_status
            self.confirmed_exit = True
        except (OSError, ValueError, ChildProcessError):
            self.identity_lost = True

    def send_signal(self, value: int) -> bool:
        if self.pidfd < 0 or self.identity is None or self.identity_lost:
            return False
        try:
            signal.pidfd_send_signal(self.pidfd, value)
            return True
        except OSError:
            return False


@dataclass(frozen=True)
class CapturePhaseUpdate:
    state: Literal["running", "terminating", "killing", "capture_ready", "quarantined", "quarantined_pending_io"]
    reason: str | None = None
    kill_action: str | None = None

    def to_record(self) -> dict:
        result = {"state": self.state}
        if self.reason is not None:
            result["reason"] = self.reason
        if self.kill_action is not None:
            result["kill_action"] = self.kill_action
        return result


@dataclass
class PreparedCaptureSlot:
    owner: OwnerInputs
    allocation: profile_api.OwnedAllocation
    parent_identity: tuple[int, int, int]
    boot_nonce: str
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
    held_fds: list[int] = field(default_factory=list)

    def expected_root(self) -> dict:
        return dict(device=self.allocation.device, inode=self.allocation.inode, mount_id=self.allocation.mount_id)

    def expected_ready(self) -> dict:
        return dict(allocation_id=self.allocation.allocation_name.removeprefix("capture-"),
                    root_identity=self.expected_root(), profile_sha256=self.owner.profile_sha256,
                    inventory_sha256=self.owner.inventory_sha256)


@dataclass
class CaptureQuarantine:
    """Live local ownership only. Unknown creation/process state is retained."""
    lane: CaptureLane
    allocation: profile_api.OwnedAllocation | profile_api.AllocationUncertain | None
    process: OwnedProcess | None
    slot: PreparedCaptureSlot | None
    reason: str
    cancel_at_ns: int | None = None
    kill_at_ns: int | None = None
    terminal_deadline_ns: int | None = None
    completion_received: bool = False
    cleanup_state: str = "blocked_pending_exit"
    held_fds: list[int] = field(default_factory=list)

    def observe_exit(self) -> None:
        """Later passive metadata observation enables removal only, not success."""
        if self.process is not None:
            self.process.observe_exit()


@dataclass(frozen=True)
class CapturePreparationFailure:
    reason: str
    quarantine: CaptureQuarantine


@dataclass(frozen=True)
class CleanupDisposition:
    state: Literal["blocked_pending_exit", "queued_owned_removal", "cleanup_incomplete", "removed"]


def request_cleanup(quarantine: CaptureQuarantine) -> CleanupDisposition:
    """Metadata-only queue admission. No removal exists in this source packet.

    A future fixed removal helper MUST consume this SAME live allocation and
    parent/root identity, compare retained parent's name to root dev/ino/mount
    before every root-level mutation, reject symlinks/mounts/special anomalies,
    cap depth24/entries16384/path512 and 20s cooperative work, and retain its own
    pidfd/finite cancellation. Only its confirmed successful exit may set removed
    and release the lane. No receipt/JSON/path can reconstruct that authority.
    """
    if quarantine.lane.occupant is not quarantine:
        return CleanupDisposition("cleanup_incomplete")
    if quarantine.cleanup_state in ("queued_owned_removal", "cleanup_incomplete", "removed"):
        return CleanupDisposition(quarantine.cleanup_state)
    if quarantine.process is not None and not quarantine.process.confirmed_exit:
        return CleanupDisposition("blocked_pending_exit")
    allocation = quarantine.allocation
    if (not isinstance(allocation, profile_api.OwnedAllocation) or allocation.root_fd < 0
            or allocation.parent_fd < 0 or allocation.parent_identity is None or allocation.boot_nonce is None
            or min(allocation.device, allocation.inode, allocation.mount_id) < 0):
        quarantine.cleanup_state = "cleanup_incomplete"
    else:
        quarantine.cleanup_state = "queued_owned_removal"
    return CleanupDisposition(quarantine.cleanup_state)


def _read_bounded(path: str, cap: int, budget: profile_api._Budget) -> bytes:
    budget.check()
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        data = bytearray()
        while len(data) <= cap:
            budget.check()
            chunk = os.read(fd, min(65536, cap + 1 - len(data)))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
        _fail("bounded identity document cap", "limit_exceeded")
    finally:
        os.close(fd)


def _sealed_document(raw: bytes, cap: int, budget: profile_api._Budget | None = None) -> int:
    if type(raw) is not bytes or len(raw) > cap:
        _fail("owner document size", "limit_exceeded")
    writer = os.memfd_create("native-capture-data", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        offset = 0
        while offset < len(raw):
            if budget is not None:
                budget.check()
            count = os.write(writer, raw[offset:offset + 65536])
            if count <= 0:
                _fail("sealed document short write")
            offset += count
        seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
        fcntl.fcntl(writer, fcntl.F_ADD_SEALS, seals)
        return os.open(f"/proc/self/fd/{writer}", os.O_RDONLY | os.O_CLOEXEC)
    finally:
        os.close(writer)


def document_metadata(fd: int, cap: int) -> None:
    info = os.fstat(fd)
    seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
    if (not stat.S_ISREG(info.st_mode) or info.st_size > cap or info.st_size < 0
            or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY
            or fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals != seals):
        _fail("sealed read-only data document required")


def _closed_helper_elf(parent: int, name: str, entry: profile_api.InventoryEntry,
                       budget: profile_api._Budget, *, interpreter: bool) -> None:
    """Conservative helper-only loader closure: static x86-64 ELF or source.

    Supporting dynamic helper installations needs separately reviewed loader
    resolution. Never assume copied lib files control host PT_INTERP/DT_NEEDED.
    This restriction does not qualify the later donor/target ELF profile.
    """
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        budget.check()
        header = os.pread(fd, 64, 0)
        if not header.startswith(b"\x7fELF"):
            if interpreter or entry.permission_class == "executable" or name.endswith(".so"):
                _fail("helper executable/native module is not supported ELF", "runtime_dependency_unavailable")
            return
        if len(header) != 64 or header[4:7] != b"\x02\x01\x01":
            _fail("helper requires ELF64 little-endian", "runtime_dependency_unavailable")
        elf_type, machine = struct.unpack_from("<HH", header, 16)
        if machine != 62 or elf_type not in (2, 3):
            _fail("helper ELF architecture/type", "runtime_dependency_unavailable")
        offset = struct.unpack_from("<Q", header, 32)[0]
        stride, count = struct.unpack_from("<HH", header, 54)
        if stride != 56 or not 0 < count <= 128 or offset + count * stride > entry.size:
            _fail("helper ELF program headers", "runtime_dependency_unavailable")
        headers = os.pread(fd, count * stride, offset)
        if len(headers) != count * stride:
            _fail("short helper ELF program headers", "runtime_dependency_unavailable")
        for index in range(count):
            budget.check()
            kind, flags, file_offset, _, _, file_size, _, _ = struct.unpack_from("<IIQQQQQQ", headers, index * stride)
            if kind == 3 or (kind == 0x6474e551 and flags & 1):
                _fail("host ELF interpreter/executable stack unsupported", "runtime_dependency_unavailable")
            if kind == 2:
                if file_size > 65536 or file_size % 16 or file_offset + file_size > entry.size:
                    _fail("helper dynamic table cap", "runtime_dependency_unavailable")
                dynamic = os.pread(fd, file_size, file_offset)
                if len(dynamic) != file_size:
                    _fail("short helper dynamic table", "runtime_dependency_unavailable")
                terminated = False
                for position in range(0, len(dynamic), 16):
                    tag, _ = struct.unpack_from("<qQ", dynamic, position)
                    if tag == 0:
                        terminated = True
                        break
                    if tag in (1, 15, 29, 0x7ffffffd, 0x7fffffff):
                        _fail("helper dynamic host dependency/search/filter unsupported", "runtime_dependency_unavailable")
                if not terminated:
                    _fail("unterminated helper dynamic table", "runtime_dependency_unavailable")
    finally:
        os.close(fd)


def _verify_installation(owner: OwnerInputs, budget: profile_api._Budget) -> str:
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
                         (CONTROLLER, binding.capture_module_sha256), (PROFILE_MODULE, binding.profile_module_sha256)):
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
            if path == ".native-capture":
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
    metadata = profile_api._open_dir(owner.installation_fd, ".native-capture", budget)
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


def _bind_process(process: OwnedProcess, owner: OwnerInputs, runtime_sha: str,
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


def _spawn_fixed(owner: OwnerInputs, descriptors: list[int]) -> int:
    """Single-threaded posix_spawn; collision-safe dup2 and explicit close set.

    No Python preexec callback. All original foreign FDs close before exec;
    nothing except 0..7 is inherited by the fixed interpreter.
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
                    if fd > 7:
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


def prepare_capture_slot(owner_inputs: OwnerInputs, preparation_deadline: int) -> PreparedCaptureSlot | CapturePreparationFailure:
    """Explicit cooperative quiescent preparation, never a scheduler poll call."""
    owner = owner_inputs
    now = time.monotonic_ns()
    deadline = min(_uint(preparation_deadline), now + 20 * NS)
    budget = profile_api._Budget(deadline / NS)
    allocation = process = slot = None
    held: list[int] = []
    channels: list[socket.socket] = []
    if owner.lane.occupant is not None:
        _fail("capture lane already owned", "runtime_dependency_unavailable")
    intent = object()
    owner.lane.occupant = intent
    try:
        if owner.quiescent is not True or threading.active_count() != 1 or owner.dedicated_supervisor_domain is not True:
            _fail("explicit quiescent trusted supervisor domain required", "supervisor_domain_unavailable")
        for name in ("pidfd_open", "P_PIDFD", "posix_spawn", "memfd_create"):
            if not hasattr(os, name):
                _fail("required Linux process facility missing", "runtime_dependency_unavailable")
        if not hasattr(signal, "pidfd_send_signal"):
            _fail("pidfd signal unavailable", "runtime_dependency_unavailable")
        if os.getuid() != os.geteuid() or os.getgid() != os.getegid():
            _fail("supervisor real/effective credentials differ", "supervisor_domain_unavailable")
        installation_anchor = os.dup(owner.installation_fd)
        held.append(installation_anchor)
        os.set_inheritable(installation_anchor, False)
        owner = replace(owner, installation_fd=installation_anchor)
        budget.check()
        try:
            runtime_sha = _verify_installation(owner, budget)
        except (OSError, profile_api.ProfileRefused) as exc:
            raise CaptureRefused("runtime_dependency_unavailable", "immutable helper installation unavailable") from exc
        _digest(owner.profile_sha256)
        _digest(owner.inventory_sha256)
        if not 0 < _uint(owner.entry_count) <= profile_api.MAX_ENTRIES or _uint(owner.total_file_bytes) > profile_api.MAX_TOTAL_BYTES:
            _fail("owner inventory totals", "limit_exceeded")
        # Canonical owner document bytes are not parsed/read as profile contents
        # before admission; metadata and independent pins were provisioned by owner.
        profile_doc = _sealed_document(owner.profile_bytes, profile_api.MAX_PROFILE_BYTES, budget)
        held.append(profile_doc)
        inventory_doc = _sealed_document(owner.inventory_bytes, profile_api.MAX_MANIFEST_BYTES, budget)
        held.append(inventory_doc)
        allocation = profile_api.allocate_private_capture(private_parent_fd=owner.private_parent_fd,
                                                          absolute_deadline=deadline / NS)
        parent_stat = os.fstat(allocation.parent_fd)
        parent_identity = (parent_stat.st_dev, parent_stat.st_ino, profile_api._mount_id(allocation.parent_fd, budget))
        donor = os.dup(owner.donor_fd)
        held.append(donor)
        os.set_inheritable(donor, False)
        if not stat.S_ISDIR(os.fstat(donor).st_mode) or fcntl.fcntl(donor, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
            _fail("owner donor directory anchor required", "root_layout_unsupported")
        parent_channel, child_channel = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC)
        channels.extend((parent_channel, child_channel))
        for channel in channels:
            channel.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        out_r, out_w = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        held.extend((out_r, out_w))
        err_r, err_w = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        held.extend((err_r, err_w))
        null = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        held.append(null)
        budget.check()
        # Mark unknown spawn disposition before entering the kernel. An error
        # without a returned PID is not proof that no child ever existed.
        process = OwnedProcess(-1)
        process.pid = _spawn_fixed(owner, [null, out_w, err_w, child_channel.fileno(), donor,
                                          allocation.root_fd, profile_doc, inventory_doc])
        # Retain process immediately; a subsequent identity failure must not
        # lose the child/allocation, or invent a numeric-PID kill fallback.
        _bind_process(process, owner, runtime_sha, budget)
        child_channel.close()
        channels.remove(child_channel)
        for fd in (out_w, err_w, null):
            os.close(fd)
            held.remove(fd)
        import secrets
        slot = PreparedCaptureSlot(owner, allocation, parent_identity, allocation.boot_nonce, secrets.token_hex(32),
                                   runtime_sha, process, parent_channel, out_r, err_r, held_fds=held)
        owner.lane.occupant = slot
        challenge = dict(profile_id=profile_api.PROFILE_ID, helper_runtime_sha256=runtime_sha, **slot.expected_ready())
        _send(slot, "CHALLENGE", 0, challenge)
        while slot.rx_seq < 2:
            budget.check()
            # Preparation only; no wait appears in capture poll/admission.
            ready = select.select([parent_channel, out_r, err_r, process.pidfd], [], [], min(0.05, max(0, (deadline - time.monotonic_ns()) / NS)))[0]
            if process.pidfd in ready:
                process.observe_exit()
                _fail("helper exited before READY", "owned_process_identity_unavailable")
            for fd in (out_r, err_r):
                if fd in ready:
                    _drain_log(slot, 0 if fd == out_r else 1, 4096)
            if parent_channel in ready:
                frame = _receive(slot)
                if frame is None:
                    _fail("helper EOF before READY")
                if frame["kind"] == "ERROR":
                    _fail(frame["payload"]["detail"], frame["payload"]["reason"])
                if slot.rx_seq == 1:
                    if frame["kind"] != "HELLO" or frame["payload"] != {"helper_runtime_sha256": runtime_sha}:
                        _fail("HELLO binding mismatch")
                elif frame["kind"] != "READY" or frame["payload"] != slot.expected_ready():
                    _fail("READY binding mismatch")
        budget.check()
        slot.prepared_at_ns = time.monotonic_ns()
        return slot
    except Exception as exc:
        if isinstance(exc, profile_api.CaptureFailed):
            allocation = exc.partial
        reason = (exc.reason if isinstance(exc, CaptureRefused) else
                  exc.code if isinstance(exc, profile_api.ProfileRefused) else "owned_process_identity_unavailable")
        # Close channels before any possible BEGIN; fixed helper exits on EOF.
        for channel in channels:
            channel.close()
        quarantine = CaptureQuarantine(owner.lane, allocation, process, slot, reason, held_fds=held)
        owner.lane.occupant = quarantine
        if process is not None and process.identity is not None:
            process.send_signal(signal.SIGKILL)
            quarantine.kill_at_ns = time.monotonic_ns()
        return CapturePreparationFailure(reason, quarantine)


def _send(slot: PreparedCaptureSlot, kind: str, seq: int, payload: dict) -> None:
    raw = encode_frame(kind, slot.nonce, seq, payload)
    if slot.tx_bytes + len(raw) > TRAFFIC_MAX:
        _fail("send traffic cap", "limit_exceeded")
    # No retry: failed/unknown delivery consumes the slot and cancels its writer.
    if slot.channel.send(raw, socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL) != len(raw):
        _fail("unknown control send disposition")
    slot.tx_bytes += len(raw)


def _receive(slot: PreparedCaptureSlot) -> dict | None:
    identity = slot.process.identity
    if identity is None or slot.process.identity_lost:
        _fail("lost process association", "owned_process_identity_unavailable")
    frame, count = receive_frame(slot.channel, peer=(identity.pid, identity.uid, identity.gid),
                                 nonce=slot.nonce, seq=slot.rx_seq)
    slot.rx_bytes += count
    if slot.rx_bytes > TRAFFIC_MAX:
        _fail("receive traffic cap", "limit_exceeded")
    if frame is not None:
        slot.rx_seq += 1
    return frame


def _drain_log(slot: PreparedCaptureSlot, index: int, cap: int) -> int:
    fd = slot.stdout_fd if index == 0 else slot.stderr_fd
    raw = os.read(fd, cap)
    slot.log_bytes[index] += len(raw)
    if slot.log_bytes[index] > 1024 * 1024 or sum(slot.log_bytes) > 2 * 1024 * 1024:
        _fail("diagnostic byte cap", "limit_exceeded")
    if not raw:
        slot.eof[index + 1] = True
    return len(raw)


@dataclass
class CaptureRun:
    slot: PreparedCaptureSlot
    capture_deadline_ns: int
    absolute_deadline_ns: int
    state: str = "copying"
    reason: str | None = None
    complete: bool = False
    complete_reported: bool = False
    cancel_at_ns: int | None = None
    kill_at_ns: int | None = None
    term_until_ns: int | None = None
    exit_until_ns: int | None = None
    taken: bool = False

    def request_cancel(self, now_ns: int, reason: str = "cancelled") -> None:
        _uint(now_ns)
        if reason not in REASONS | {"cancelled"}:
            _fail("invalid local cancellation reason")
        if self.taken or self.reason is not None:
            return
        self.reason = reason
        self.complete = False
        self.cancel_at_ns = now_ns
        self.term_until_ns = min(now_ns + 5 * NS, self.capture_deadline_ns, self.absolute_deadline_ns)
        self.exit_until_ns = min(self.term_until_ns + 5 * NS, self.capture_deadline_ns, self.absolute_deadline_ns)
        self.state = "terminating"
        self.slot.process.send_signal(signal.SIGTERM)

    def _advance_cancel(self, now_ns: int) -> None:
        if self.reason is None:
            return
        process = self.slot.process
        if process.confirmed_exit:
            self.state = "quarantined"
            return
        if now_ns >= self.term_until_ns and self.kill_at_ns is None:
            process.send_signal(signal.SIGKILL)
            self.kill_at_ns = now_ns
            self.state = "killing"
        if now_ns >= self.exit_until_ns:
            self.state = "quarantined_pending_io"

    def poll(self, now_ns: int) -> CapturePhaseUpdate:
        """At most16 metadata events/64KiB/5ms; no filesystem traversal or wait."""
        _uint(now_ns)
        if self.taken:
            _fail("capture handle transferred")
        start = time.monotonic_ns()
        now_ns = max(now_ns, start)
        if self.reason is None and (self.slot.process.identity_lost or self.slot.process.identity is None):
            self.request_cancel(now_ns, "owned_process_identity_unavailable")
        if self.reason is None and now_ns >= self.capture_deadline_ns:
            self.request_cancel(now_ns, "deadline_exceeded")
        bytes_left = 65536
        events = 0
        slot = self.slot
        while events < 16 and bytes_left > FRAME_MAX and time.monotonic_ns() - start < 5_000_000:
            sources = ([slot.channel] if not slot.eof[0] else [])
            sources += [fd for index, fd in enumerate((slot.stdout_fd, slot.stderr_fd)) if not slot.eof[index + 1]]
            if slot.process.pidfd >= 0 and not slot.process.confirmed_exit and not slot.process.identity_lost:
                sources.append(slot.process.pidfd)
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
                events += 1
                try:
                    if source is slot.channel:
                        # Reserve worst-case bytes even if malformed decoding
                        # raises, so hostile packets cannot evade this poll cap.
                        bytes_left -= FRAME_MAX + 1
                        frame = _receive(slot)
                        if frame is None:
                            slot.eof[0] = True
                            if not self.complete:
                                _fail("EOF without COMPLETE")
                        elif self.complete or self.reason is not None:
                            _fail("post-terminal frame")
                        elif frame["kind"] == "ERROR":
                            _fail(frame["payload"]["detail"], frame["payload"]["reason"])
                        elif frame["kind"] != "COMPLETE" or frame["payload"] != dict(
                                **slot.expected_ready(), entry_count=slot.owner.entry_count,
                                total_file_bytes=slot.owner.total_file_bytes):
                            _fail("COMPLETE mismatch")
                        else:
                            self.complete = True
                            self.complete_reported = True
                            self.state = "completion_pending_exit"
                    elif source == slot.process.pidfd:
                        slot.process.observe_exit()
                        if slot.process.identity_lost:
                            _fail("owned reap association lost", "owned_process_identity_unavailable")
                    else:
                        bytes_left -= _drain_log(slot, 0 if source == slot.stdout_fd else 1, min(4096, bytes_left))
                except BlockingIOError:
                    pass
                except (OSError, CaptureRefused) as exc:
                    self.request_cancel(max(now_ns, time.monotonic_ns()), exc.reason if isinstance(exc, CaptureRefused) else "ipc_binding_invalid")
            if slot.process.identity_lost and self.reason is None:
                self.request_cancel(max(now_ns, time.monotonic_ns()), "owned_process_identity_unavailable")
        end = max(now_ns, time.monotonic_ns())
        if self.reason is None and end >= self.capture_deadline_ns:
            self.request_cancel(end, "deadline_exceeded")
        if self.reason is None and slot.process.confirmed_exit and slot.process.exit_code != 0:
            self.request_cancel(end, "capture_integrity_failed")
        if self.reason is None and slot.process.confirmed_exit and all(slot.eof):
            if self.complete and slot.process.exit_code == 0:
                self.state = "capture_ready"
            else:
                self.request_cancel(end, "ipc_binding_invalid")
        self._advance_cancel(end)
        if self.state == "quarantined_pending_io":
            return CapturePhaseUpdate(self.state, self.reason, "kill-failed")
        if self.state == "quarantined":
            return CapturePhaseUpdate(self.state, self.reason)
        return CapturePhaseUpdate(self.state if self.state in ("terminating", "killing", "capture_ready") else "running")

    def take_capture(self) -> profile_api.OwnedCapture:
        if (self.taken or self.state != "capture_ready" or self.reason is not None or not self.complete
                or not self.slot.process.confirmed_exit or self.slot.process.exit_code != 0
                or self.slot.process.identity is None or self.slot.process.identity_lost or not all(self.slot.eof)):
            _fail("capture not available once")
        if time.monotonic_ns() >= self.capture_deadline_ns:
            self.request_cancel(time.monotonic_ns(), "deadline_exceeded")
            _fail("late capture adoption", "deadline_exceeded")
        self.taken = True
        allocation = self.slot.allocation
        result = profile_api.OwnedCapture(allocation.allocation_name, allocation.root_fd, allocation.parent_fd,
                                         allocation.device, allocation.inode, allocation.mount_id,
                                         profile_api.CaptureIdentity(self.slot.owner.profile_sha256, self.slot.owner.inventory_sha256,
                                                                     allocation.device, allocation.inode, allocation.mount_id),
                                         parent_identity=allocation.parent_identity, boot_nonce=allocation.boot_nonce)
        allocation.root_fd = allocation.parent_fd = -1
        # The later lifecycle owns the lane until consumption/removal/registry
        # transfer. A ready capture does not implicitly release admission.
        self.slot.owner.lane.occupant = result
        _close_transport(self.slot)
        return result

    def take_quarantine(self) -> CaptureQuarantine:
        if self.taken or self.state not in ("quarantined", "quarantined_pending_io"):
            _fail("quarantine not available once")
        self.taken = True
        quarantine = CaptureQuarantine(self.slot.owner.lane, self.slot.allocation, self.slot.process, self.slot,
                                        self.reason or "capture_integrity_failed", self.cancel_at_ns, self.kill_at_ns,
                                        self.exit_until_ns, self.complete_reported)
        self.slot.owner.lane.occupant = quarantine
        return quarantine


def _close_transport(slot: PreparedCaptureSlot) -> None:
    slot.channel.close()
    for fd in slot.held_fds:
        os.close(fd)
    slot.held_fds.clear()
    if slot.process.pidfd >= 0:
        os.close(slot.process.pidfd)
        slot.process.pidfd = -1


def begin_capture(slot: PreparedCaptureSlot, seed_timing: dict) -> CaptureRun:
    """One-use admission: only local metadata and one nonblocking BEGIN send."""
    if slot.used or slot.owner.lane.occupant is not slot:
        _fail("prepared slot already consumed")
    slot.used = True
    now = time.monotonic_ns()
    run = CaptureRun(slot, now, now)
    slot.owner.lane.occupant = run
    try:
        _exact(seed_timing, "admitted_at_ns absolute_deadline_ns")
        admitted = _uint(seed_timing["admitted_at_ns"])
        absolute = _uint(seed_timing["absolute_deadline_ns"])
        if absolute - admitted != 600 * NS or admitted > now:
            _fail("seed must retain original 600s admission", "deadline_exceeded")
        run.absolute_deadline_ns = absolute
        run.capture_deadline_ns = min(now + 90 * NS, absolute - 510 * NS)
        if (slot.prepared_at_ns <= 0 or now >= slot.prepared_at_ns + 30 * NS
                or now >= run.capture_deadline_ns):
            _fail("expired prepared slot/capture reservation", "deadline_exceeded")
        # OwnerInputs/HelperRuntimeBinding are frozen and retained by identity;
        # compare canonical binding once without any document/filesystem reads.
        if _hash(slot.owner.helper_binding.canonical_bytes()) != slot.runtime_sha256:
            _fail("coherent owner binding changed", "profile_pin_mismatch")
        _send(slot, "BEGIN", 1, dict(capture_deadline_ns=run.capture_deadline_ns, absolute_deadline_ns=absolute))
    except Exception as exc:
        run.request_cancel(now, exc.reason if isinstance(exc, CaptureRefused) else "ipc_binding_invalid")
    return run


def expire_prepared_slot(slot: PreparedCaptureSlot, now_ns: int) -> CaptureRun:
    """Maintenance must retire idle slots even when no job is admitted."""
    if slot.used or slot.owner.lane.occupant is not slot:
        _fail("prepared slot already consumed")
    _uint(now_ns)
    if now_ns < slot.prepared_at_ns + 30 * NS:
        _fail("prepared slot has not expired")
    slot.used = True
    run = CaptureRun(slot, now_ns + 10 * NS, now_ns + 10 * NS)
    slot.owner.lane.occupant = run
    run.request_cancel(now_ns, "deadline_exceeded")
    return run
