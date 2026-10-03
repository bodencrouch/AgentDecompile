"""Fixed immutable helper entry. No task module, donor execution or subprocess.

Installed only at <owner immutable root>/app/native_capture_entry.py. Invoked
with that installation's usr/bin/python3.12 -I -S -B. This file must never be
launched from a workspace as a shortcut to runtime qualification.
"""
from __future__ import annotations

import sys


def main() -> int:
    # sys is built in; os is frozen in the pinned CPython installation. Replace
    # all source search paths before importing any source-backed helper module.
    import os
    if (sys.flags.isolated != 1 or sys.flags.no_site != 1 or not sys.dont_write_bytecode
            or not __file__.endswith("/app/native_capture_entry.py")):
        return 70
    installation = __file__[:-len("/app/native_capture_entry.py")]
    if not installation or not installation.startswith("/"):
        return 70
    sys.path[:] = [installation + "/usr/lib/python3.12", installation + "/usr/lib/python3.12/lib-dynload"]
    if dict(os.environ) != {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}:
        return 70
    os.chdir(installation)
    import importlib.util
    # Fixed private module names and fixed filenames only. No package initializer
    # runs, and there is no generic loader API available over private IPC.
    for name, filename in (("_native_closure_profile", "native_closure_profile.py"),
                           ("_native_capture", "native_capture.py")):
        spec = importlib.util.spec_from_file_location(name, installation + "/app/" + filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    capture = sys.modules["_native_capture"]
    profile = sys.modules["_native_closure_profile"]
    import ctypes
    import fcntl
    import resource
    import select
    import signal
    import socket
    import stat
    import time

    channel = None
    nonce = None
    sequence = 0
    sent = 0
    deadline = time.monotonic_ns() + 20 * capture.NS
    parent_pid = os.getppid()
    peer = (parent_pid, os.geteuid(), os.getegid())
    try:
        # Fixed Linux parent-death SIGKILL, with the reparenting race checked.
        # pidfd does not promise immediate termination of blocked kernel I/O.
        if parent_pid <= 1:
            capture._fail("parent disappeared", "owned_process_identity_unavailable")
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, int(signal.SIGKILL), 0, 0, 0) != 0 or os.getppid() != parent_pid:
            capture._fail("parent death association unavailable", "owned_process_identity_unavailable")
        # No network socket is created. This wraps only inherited private FD3.
        channel = socket.socket(fileno=3)
        channel.setblocking(False)
        if (channel.family != socket.AF_UNIX or channel.type & 0xf != socket.SOCK_SEQPACKET
                or channel.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1):
            capture._fail("fixed private seqpacket required")
        # Verify inherited descriptors before any profile/donor contents read.
        existing = []
        with os.scandir("/proc/self/fd") as scan:
            names = [entry.name for entry in scan]
        for name in names:
            if name.isdigit():
                try:
                    fcntl.fcntl(int(name), fcntl.F_GETFD)
                    existing.append(int(name))
                except OSError:
                    pass
        if sorted(existing) != list(range(8)):
            capture._fail("unexpected inherited descriptor")
        null = os.fstat(0)
        if (not stat.S_ISCHR(null.st_mode) or os.major(null.st_rdev) != 1 or os.minor(null.st_rdev) != 3
                or fcntl.fcntl(0, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY):
            capture._fail("stdin must be read-only null")
        for fd in (1, 2):
            if not stat.S_ISFIFO(os.fstat(fd).st_mode):
                capture._fail("diagnostics require separate pipes")
        if (os.fstat(1).st_dev, os.fstat(1).st_ino) == (os.fstat(2).st_dev, os.fstat(2).st_ino):
            capture._fail("diagnostic streams alias")
        for fd in range(3, 8):
            os.set_inheritable(fd, False)
        for fd in (4, 5):
            if not stat.S_ISDIR(os.fstat(fd).st_mode) or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
                capture._fail("inherited directory anchor required")
        capture.document_metadata(6, profile.MAX_PROFILE_BYTES)
        capture.document_metadata(7, profile.MAX_MANIFEST_BYTES)

        def wait_frame(expected_sequence: int, until: int) -> dict:
            while time.monotonic_ns() < until:
                if os.getppid() != parent_pid:
                    capture._fail("parent relationship lost", "owned_process_identity_unavailable")
                if select.select([channel], [], [], min(0.05, max(0, (until - time.monotonic_ns()) / capture.NS)))[0]:
                    frame, _ = capture.receive_frame(channel, peer=peer, nonce=nonce, seq=expected_sequence)
                    if frame is None:
                        capture._fail("parent EOF")
                    return frame
            capture._fail("helper protocol deadline", "deadline_exceeded")

        def send(kind: str, payload: dict) -> None:
            nonlocal sequence, sent
            raw = capture.encode_frame(kind, nonce, sequence, payload)
            if sent + len(raw) > capture.TRAFFIC_MAX:
                capture._fail("helper traffic cap", "limit_exceeded")
            # Small fixed packets; no blocking/retry with uncertain delivery.
            if channel.send(raw, socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL) != len(raw):
                capture._fail("helper send uncertain")
            sequence += 1
            sent += len(raw)

        challenge = wait_frame(0, deadline)
        if challenge["kind"] != "CHALLENGE":
            capture._fail("expected CHALLENGE")
        nonce = challenge["nonce"]
        pins = challenge["payload"]
        try:
            for limit, value in ((resource.RLIMIT_CORE, 0), (resource.RLIMIT_NOFILE, 128),
                                 (resource.RLIMIT_FSIZE, profile.MAX_FILE_BYTES), (resource.RLIMIT_AS, 2 * 1024**3),
                                 (resource.RLIMIT_CPU, 90), (resource.RLIMIT_NPROC, 32)):
                resource.setrlimit(limit, (value, value))
                if resource.getrlimit(limit) != (value, value):
                    capture._fail("required hard/soft limit unavailable", "runtime_dependency_unavailable")
        except (AttributeError, OSError, ValueError) as exc:
            if isinstance(exc, capture.CaptureRefused):
                raise
            raise capture.CaptureRefused("runtime_dependency_unavailable", "required hard/soft limit unsupported") from exc
        budget = profile._Budget(deadline / capture.NS)
        # These are helper-installation metadata, never donor/profile documents.
        binding_raw = capture._read_bounded(installation + "/" + capture.BINDING_DOCUMENT, 4096, budget)
        binding_record = capture._exact(capture._json(binding_raw),
                                       "schema runtime_inventory_sha256 interpreter_sha256 entry_sha256 capture_module_sha256 profile_module_sha256 environment_sha256")
        binding = capture.HelperRuntimeBinding(**binding_record)
        if capture._hash(binding.canonical_bytes()) != pins["helper_runtime_sha256"]:
            capture._fail("helper runtime binding disagrees", "profile_pin_mismatch")
        root = os.open(installation, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            if not os.fstatvfs(root).f_flag & os.ST_RDONLY:
                capture._fail("helper installation is mutable", "runtime_dependency_unavailable")
        finally:
            os.close(root)
        # Parent has authenticated the complete immutable installation. Independently
        # corroborate actual helper roles here; a HELLO echo alone is not authority.
        for relative, expected in ((capture.ENTRY, binding.entry_sha256),
                                   (capture.CONTROLLER, binding.capture_module_sha256),
                                   (capture.PROFILE_MODULE, binding.profile_module_sha256)):
            raw = capture._read_bounded(installation + "/" + relative, 1024 * 1024, budget)
            if capture._hash(raw) != expected:
                capture._fail("actual helper source binding mismatch", "profile_pin_mismatch")
        root_stat = os.fstat(5)
        identity = dict(device=root_stat.st_dev, inode=root_stat.st_ino, mount_id=profile._mount_id(5, budget))
        if (identity != pins["root_identity"] or root_stat.st_uid != os.geteuid()
                or stat.S_IMODE(root_stat.st_mode) != 0o700):
            capture._fail("inherited fresh root identity mismatch")
        send("HELLO", {"helper_runtime_sha256": pins["helper_runtime_sha256"]})
        ready = {key: pins[key] for key in ("allocation_id", "root_identity", "profile_sha256", "inventory_sha256")}
        send("READY", ready)
        # Fresh prepared slot is single use. No donor/profile reads before BEGIN.
        begin = wait_frame(1, time.monotonic_ns() + 30 * capture.NS)
        if begin["kind"] != "BEGIN":
            capture._fail("expected BEGIN")
        timing = begin["payload"]
        now = time.monotonic_ns()
        deadline = timing["capture_deadline_ns"]
        if (not now < deadline <= now + 90 * capture.NS
                or deadline > timing["absolute_deadline_ns"] - 510 * capture.NS):
            capture._fail("capture phase reservation", "deadline_exceeded")
        budget = profile._Budget(deadline / capture.NS)

        def read_document(fd: int, cap: int) -> bytes:
            capture.document_metadata(fd, cap)
            result = bytearray()
            while len(result) <= cap:
                budget.check()
                chunk = os.read(fd, min(65536, cap + 1 - len(result)))
                if not chunk:
                    return bytes(result)
                result.extend(chunk)
            capture._fail("document read limit", "limit_exceeded")

        selected = profile.load_profile(read_document(6, profile.MAX_PROFILE_BYTES),
                                        read_document(7, profile.MAX_MANIFEST_BYTES),
                                        expected_profile_sha256=pins["profile_sha256"],
                                        expected_inventory_sha256=pins["inventory_sha256"])
        copied = profile.capture_into_owned(selected, donor_fd=4,
                                            allocation=profile.CaptureRootView(5, **identity),
                                            absolute_deadline=deadline / capture.NS)
        budget.check()
        send("COMPLETE", dict(**ready, entry_count=copied.entry_count, total_file_bytes=copied.total_file_bytes))
        return 0
    except Exception as exc:
        if channel is not None and nonce is not None and sequence <= 2:
            reason = (exc.reason if isinstance(exc, capture.CaptureRefused) else
                      exc.code if isinstance(exc, profile.ProfileRefused) else "capture_integrity_failed")
            if reason not in capture.REASONS:
                reason = "capture_integrity_failed"
            try:
                # No exception repr, paths, traceback, pickle or arbitrary detail.
                send("ERROR", {"reason": reason, "detail": "fixed capture helper refused"})
            except Exception:
                pass
        return 70
    finally:
        if channel is not None:
            channel.close()
        for fd in (0, 1, 2, 4, 5, 6, 7):
            try:
                os.close(fd)
            except OSError:
                pass


if __name__ == "__main__":
    # Immediate fixed exit: no unrelated module atexit handlers or writers.
    import os
    os._exit(main())
