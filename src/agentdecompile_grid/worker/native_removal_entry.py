"""Fixed immutable six-descriptor removal entry, never a workspace launcher.

Only the owner's self-contained static installation may launch this source.
No donor content, profile/task document, generic dispatcher or child process.
"""
from __future__ import annotations

import sys


def main() -> int:
    import os
    suffix = "/app/native_removal_entry.py"
    if (sys.flags.isolated != 1 or sys.flags.no_site != 1 or not sys.dont_write_bytecode
            or not __file__.endswith(suffix)):
        return 70
    installation = __file__[:-len(suffix)]
    if not installation or not installation.startswith("/"):
        return 70
    sys.path[:] = [installation + "/usr/lib/python3.12", installation + "/usr/lib/python3.12/lib-dynload"]
    if dict(os.environ) != {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}:
        return 70
    os.chdir(installation)
    import importlib.util
    for name, filename in (("_native_closure_profile", "native_closure_profile.py"),
                           ("_native_capture", "native_capture.py"),
                           ("_native_removal", "native_removal.py")):
        spec = importlib.util.spec_from_file_location(name, installation + "/app/" + filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    removal = sys.modules["_native_removal"]
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
    sequence = sent = received = 0
    terminal = False
    deadline = time.monotonic_ns() + 20 * removal.NS
    parent_pid = os.getppid()
    peer = (parent_pid, os.geteuid(), os.getegid())
    try:
        if parent_pid <= 1:
            removal._fail("parent disappeared", "owned_process_identity_unavailable")
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, int(signal.SIGKILL), 0, 0, 0) != 0 or os.getppid() != parent_pid:
            removal._fail("parent death association unavailable", "owned_process_identity_unavailable")
        channel = socket.socket(fileno=3)
        channel.setblocking(False)
        if (channel.family != socket.AF_UNIX or channel.type & 0xf != socket.SOCK_SEQPACKET
                or channel.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1):
            removal._fail("fixed private seqpacket required")
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
        if sorted(existing) != list(range(6)):
            removal._fail("unexpected inherited descriptor")
        null = os.fstat(0)
        if (not stat.S_ISCHR(null.st_mode) or os.major(null.st_rdev) != 1 or os.minor(null.st_rdev) != 3
                or fcntl.fcntl(0, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY):
            removal._fail("stdin must be read-only null")
        for fd in (1, 2):
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            if (not stat.S_ISFIFO(os.fstat(fd).st_mode) or not flags & os.O_NONBLOCK
                    or flags & os.O_ACCMODE != os.O_WRONLY):
                removal._fail("diagnostics require nonblocking write pipes")
        if (os.fstat(1).st_dev, os.fstat(1).st_ino) == (os.fstat(2).st_dev, os.fstat(2).st_ino):
            removal._fail("diagnostic streams alias")
        for fd in range(3, 6):
            os.set_inheritable(fd, False)
        for fd in (4, 5):
            if (not stat.S_ISDIR(os.fstat(fd).st_mode)
                    or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY):
                removal._fail("inherited directory anchor required")

        def wait_frame(expected_sequence: int) -> dict:
            nonlocal received
            while time.monotonic_ns() < deadline:
                if os.getppid() != parent_pid:
                    removal._fail("parent relationship lost", "owned_process_identity_unavailable")
                if select.select([channel], [], [], min(0.05, max(0, (deadline - time.monotonic_ns()) / removal.NS)))[0]:
                    frame, count = removal.receive_frame(channel, peer=peer, nonce=nonce, seq=expected_sequence)
                    received += count
                    if received > removal.TRAFFIC_MAX:
                        removal._fail("parent traffic cap", "limit_exceeded")
                    if frame is None:
                        removal._fail("parent EOF")
                    if time.monotonic_ns() >= deadline:
                        removal._fail("late parent frame", "deadline_exceeded")
                    return frame
            removal._fail("helper protocol deadline", "deadline_exceeded")

        def send(kind: str, payload: dict) -> None:
            nonlocal sequence, sent, terminal
            if terminal:
                removal._fail("duplicate terminal message")
            raw = removal.encode_frame(kind, nonce, sequence, payload)
            if sent + len(raw) > removal.TRAFFIC_MAX:
                removal._fail("helper traffic cap", "limit_exceeded")
            if kind in ("COMPLETE", "ERROR"):
                terminal = True  # Unknown delivery is terminal too.
            if channel.send(raw, socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL) != len(raw):
                removal._fail("helper send uncertain")
            sequence += 1
            sent += len(raw)

        challenge = wait_frame(0)
        if challenge["kind"] != "CHALLENGE":
            removal._fail("expected CHALLENGE")
        nonce = challenge["nonce"]
        pins = challenge["payload"]
        now = time.monotonic_ns()
        deadline = pins["attempt_deadline_ns"]
        if not now < deadline <= now + 20 * removal.NS:
            removal._fail("attempt bootstrap deadline", "deadline_exceeded")
        budget = removal._Budget(deadline)
        for limit, value in ((resource.RLIMIT_CORE, 0), (resource.RLIMIT_NOFILE, 128),
                             (resource.RLIMIT_FSIZE, 0), (resource.RLIMIT_AS, 2 * 1024**3),
                             (resource.RLIMIT_CPU, 20), (resource.RLIMIT_NPROC, 32)):
            budget.check()
            try:
                resource.setrlimit(limit, (value, value))
                if resource.getrlimit(limit) != (value, value):
                    removal._fail("required hard/soft limit unavailable", "runtime_dependency_unavailable")
            except (AttributeError, OSError, ValueError) as exc:
                raise removal.RemovalRefused("runtime_dependency_unavailable", "required limits unavailable") from exc
            budget.check()
        binding_raw = removal._read_bounded(installation + "/" + removal.BINDING_DOCUMENT, 4096, budget)
        record = removal._exact(removal._json(binding_raw),
                                 "schema runtime_inventory_sha256 interpreter_sha256 entry_sha256 removal_module_sha256 capture_module_sha256 profile_module_sha256 environment_sha256")
        binding = removal.RemovalRuntimeBinding(**record)
        if removal._hash(binding.canonical_bytes()) != pins["helper_runtime_sha256"]:
            removal._fail("helper runtime binding disagrees", "profile_pin_mismatch")
        root = os.open(installation, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            budget.check()
            if not os.fstatvfs(root).f_flag & os.ST_RDONLY:
                removal._fail("helper installation is mutable", "runtime_dependency_unavailable")
        finally:
            os.close(root)
        for relative, expected in ((removal.ENTRY, binding.entry_sha256),
                                   (removal.CONTROLLER, binding.removal_module_sha256),
                                   (removal.CAPTURE_MODULE, binding.capture_module_sha256),
                                   (removal.PROFILE_MODULE, binding.profile_module_sha256)):
            raw = removal._read_bounded(installation + "/" + relative, 1024 * 1024, budget)
            if removal._hash(raw) != expected:
                removal._fail("actual helper source binding mismatch", "profile_pin_mismatch")
            budget.check()
        if os.getppid() != parent_pid:
            removal._fail("parent relationship lost", "owned_process_identity_unavailable")
        view = removal.RemovalRootView(4, 5, pins["allocation_id"], pins["parent_identity"], pins["root_identity"])
        removal._guard_root(view, budget)
        send("HELLO", {"helper_runtime_sha256": pins["helper_runtime_sha256"]})
        ready = {key: pins[key] for key in ("allocation_id", "root_identity", "parent_identity")}
        budget.check()
        send("READY", ready)
        begin = wait_frame(1)
        if begin["kind"] != "BEGIN":
            removal._fail("expected BEGIN")
        timing = begin["payload"]
        now = time.monotonic_ns()
        if (timing["removal_deadline_ns"] != deadline or not now < deadline <= now + 20 * removal.NS
                or deadline > timing["deadline_ceiling_ns"]):
            removal._fail("removal deadline changed", "deadline_exceeded")
        summary = removal.remove_owned_tree(view, deadline_ns=deadline)
        budget.check()
        if os.getppid() != parent_pid:
            removal._fail("parent relationship lost", "owned_process_identity_unavailable")
        send("COMPLETE", dict(**ready, removed_entries=summary.removed_entries, root_unlinked=summary.root_unlinked))
        budget.check()
        return 0
    except Exception as exc:
        if channel is not None and nonce is not None and not terminal:
            try:
                send("ERROR", {"reason": removal._reason(exc), "detail": "fixed removal helper refused"})
            except Exception:
                pass
        return 70
    finally:
        if channel is not None:
            channel.close()
        for fd in (0, 1, 2, 4, 5):
            try:
                os.close(fd)
            except OSError:
                pass


if __name__ == "__main__":
    import os
    os._exit(main())
