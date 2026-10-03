"""Task11.6c future regression specifications: authored, NOT run or collected.

Transport/process/clock models below specify Python state transitions only.
Benign temporary-tree definitions call the real removal primitive, but no fixture
was invoked during authorship. Neither model nor AST checks qualify actual
credentials, mounts, helper startup, pidfd reaping or physical directory removal.
"""
from __future__ import annotations

import array
import ast
import json
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from agentdecompile_grid.worker import native_capture as capture
from agentdecompile_grid.worker import native_closure_profile as profile
from agentdecompile_grid.worker import native_removal as removal


NONCE = "a" * 64
ALLOCATION = "b" * 32
ROOT = {"device": 11, "inode": 12, "mount_id": 13}
PARENT = {"device": 11, "inode": 22, "mount_id": 13}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode()


def payload(kind):
    anchors = dict(allocation_id=ALLOCATION, root_identity=dict(ROOT), parent_identity=dict(PARENT))
    return {
        "CHALLENGE": dict(**anchors, helper_runtime_sha256="c" * 64, attempt_deadline_ns=120_000_000_000),
        "HELLO": {"helper_runtime_sha256": "c" * 64},
        "READY": anchors,
        "BEGIN": {"removal_deadline_ns": 120_000_000_000, "deadline_ceiling_ns": 600_000_000_000},
        "COMPLETE": dict(**anchors, removed_entries=3, root_unlinked=True),
        "ERROR": {"reason": "cleanup_incomplete", "detail": "removal refused"},
    }[kind]


@pytest.mark.parametrize("kind", ["CHALLENGE", "HELLO", "READY", "BEGIN", "COMPLETE", "ERROR"])
def test_removal_codec_exact_canonical_frames_remain_separate_from_capture(kind):
    raw = removal.encode_frame(kind, NONCE, 0, payload(kind))
    value = removal.decode_frame(raw, nonce=NONCE, seq=0)
    assert value == dict(schema="agentdecompile.native-removal-ipc.v1", kind=kind,
                         nonce=NONCE, seq=0, payload=payload(kind))
    assert raw == canonical(value)
    with pytest.raises(capture.CaptureRefused):
        capture.decode_frame(raw, nonce=NONCE, seq=0)


@pytest.mark.parametrize("fault", ["wrong_nonce", "replay", "bool_seq", "overflow", "float",
                                   "extra_field", "missing_parent", "bool_mount", "negative_inode",
                                   "root_unlinked_integer", "root_unlinked_false", "entry_cap",
                                   "caller_path", "capture_schema", "cancelled_wire_reason"])
def test_removal_codec_refuses_forged_authority(fault):
    value = dict(schema=removal.SCHEMA, kind="COMPLETE", nonce=NONCE, seq=2, payload=payload("COMPLETE"))
    if fault == "wrong_nonce":
        value["nonce"] = "f" * 64
    elif fault in {"replay", "bool_seq", "overflow", "float"}:
        value["seq"] = {"replay": 1, "bool_seq": True, "overflow": 2**64, "float": 2.0}[fault]
    elif fault == "extra_field":
        value["payload"]["root_fd"] = 701
    elif fault == "missing_parent":
        del value["payload"]["parent_identity"]
    elif fault == "bool_mount":
        value["payload"]["parent_identity"]["mount_id"] = True
    elif fault == "negative_inode":
        value["payload"]["root_identity"]["inode"] = -1
    elif fault.startswith("root_unlinked_"):
        value["payload"]["root_unlinked"] = 1 if fault.endswith("integer") else False
    elif fault == "entry_cap":
        value["payload"]["removed_entries"] = 16_385
    elif fault == "caller_path":
        value["payload"]["allocation_id"] = "../sibling"
    elif fault == "capture_schema":
        value["schema"] = capture.SCHEMA
    else:
        value["kind"] = "ERROR"
        value["payload"] = {"reason": "cancelled", "detail": "local reason is not a wire reason"}
    with pytest.raises(removal.RemovalRefused):
        removal.decode_frame(canonical(value), nonce=NONCE, seq=2)


@pytest.mark.parametrize("fault", ["duplicate", "whitespace", "utf8", "nan", "surrogate", "depth", "members", "bytes"])
def test_removal_parser_caps_precede_unbounded_decoding(fault):
    raw = removal.encode_frame("HELLO", NONCE, 0, payload("HELLO"))
    specimens = {
        "duplicate": raw.replace(b'"seq":0', b'"seq":0,"seq":0'),
        "whitespace": raw + b"\n",
        "utf8": raw.replace(b'"HELLO"', b'"\xff"'),
        "nan": raw.replace(b'"seq":0', b'"seq":NaN'),
        "surrogate": raw.replace(b'"HELLO"', b'"\\ud800"'),
        "depth": b'{"a":{"b":{"c":{"d":{"e":0}}}}}',
        "members": canonical({str(index): 0 for index in range(65)}),
        "bytes": b" " * 4097,
    }
    with pytest.raises(removal.RemovalRefused) as error:
        removal.decode_frame(specimens[fault], nonce=NONCE, seq=0)
    assert error.value.reason == ("limit_exceeded" if fault in {"depth", "members", "bytes"} else "ipc_binding_invalid")


def test_complete_entry_cap_and_error_detail_exact_boundaries():
    complete = dict(payload("COMPLETE"), removed_entries=16_384)
    assert removal.decode_frame(removal.encode_frame("COMPLETE", NONCE, 2, complete),
                                nonce=NONCE, seq=2)["payload"] == complete
    detail = dict(reason="cleanup_incomplete", detail="é" * 128)
    assert removal.decode_frame(removal.encode_frame("ERROR", NONCE, 2, detail),
                                nonce=NONCE, seq=2)["payload"] == detail
    for invalid in ("é" * 129, "\0"):
        with pytest.raises(removal.RemovalRefused):
            removal.encode_frame("ERROR", NONCE, 2, dict(detail, detail=invalid))


class DatagramModel:
    """Explicit synthetic datagrams; never kernel credential evidence."""
    def __init__(self):
        self.packets = []
        self.sent = []
        self.closed = False
        self.send_fault = None
        self.received = 0

    def recvmsg(self, size, ancillary_size, flags):
        assert size == 4097 and ancillary_size == socket.CMSG_SPACE(256 * 4)
        assert flags == socket.MSG_CMSG_CLOEXEC
        if not self.packets:
            raise BlockingIOError()
        self.received += 1
        return self.packets.pop(0)

    def send(self, raw, flags):
        assert flags == socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL
        self.sent.append(raw)
        if isinstance(self.send_fault, Exception):
            raise self.send_fault
        return len(raw) if self.send_fault is None else self.send_fault

    def close(self):
        self.closed = True


def credentials(peer):
    return socket.SOL_SOCKET, socket.SCM_CREDENTIALS, struct.pack("3i", *peer)


@pytest.mark.parametrize("fault", [None, "missing", "wrong_pid", "duplicate", "rights", "truncated_rights", "truncated_frame"])
def test_removal_credentials_and_delivered_rights_preserve_foreign_handles(monkeypatch, fault):
    channel = DatagramModel()
    ancillary, flags = [credentials((41, 42, 43))], 0
    if fault == "missing":
        ancillary = []
    elif fault == "wrong_pid":
        ancillary = [credentials((99, 42, 43))]
    elif fault == "duplicate":
        ancillary *= 2
    elif fault in {"rights", "truncated_rights"}:
        ancillary.append((socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [801, 802]).tobytes()))
        flags = socket.MSG_CTRUNC if fault == "truncated_rights" else 0
    elif fault == "truncated_frame":
        flags = socket.MSG_TRUNC
    raw = removal.encode_frame("HELLO", NONCE, 0, payload("HELLO"))
    channel.packets.append((raw, ancillary, flags, None))
    closed = []
    monkeypatch.setattr(removal.os, "close", closed.append)
    if fault is None:
        assert removal.receive_frame(channel, peer=(41, 42, 43), nonce=NONCE, seq=0)[0]["kind"] == "HELLO"
    else:
        with pytest.raises(removal.RemovalRefused):
            removal.receive_frame(channel, peer=(41, 42, 43), nonce=NONCE, seq=0)
    assert closed == ([801, 802] if fault in {"rights", "truncated_rights"} else [])
    assert 803 not in closed


@pytest.fixture
def benign_tree(tmp_path):
    """Future real primitive fixture; no helper/runtime and no executed evidence.

    Teardown restores only explicitly retained fixture directory descriptors.
    No wildcard walk, recursive chmod, generic removal or production tombstone.
    """
    parent, donor, foreign = (tmp_path / name for name in ("private", "donor", "foreign"))
    for directory in (parent, donor, foreign):
        directory.mkdir(mode=0o700)
    (foreign / "sentinel").write_bytes(b"foreign bytes")
    (donor / "sentinel").write_bytes(b"donor bytes")
    (parent / "sibling").mkdir(mode=0o700)
    (parent / "sibling" / "sentinel").write_bytes(b"sibling bytes")
    name = "capture-" + ALLOCATION
    root = parent / name
    root.mkdir(mode=0o700)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent_fd, root_fd, foreign_fd, donor_fd = [os.open(path, flags) for path in (parent, root, foreign, donor)]
    handles = [parent_fd, root_fd, foreign_fd, donor_fd]
    directories = [root_fd]
    budget = profile._Budget(time.monotonic() + 20)

    def identity(fd):
        info = os.fstat(fd)
        return dict(device=info.st_dev, inode=info.st_ino, mount_id=profile._mount_id(fd, budget))

    view = removal.RemovalRootView(parent_fd, root_fd, ALLOCATION, identity(parent_fd), identity(root_fd))

    def mkdir(relative, mode=0o700):
        directory = root / relative
        directory.mkdir(mode=mode)
        fd = os.open(directory, flags)
        handles.append(fd)
        directories.append(fd)
        return directory

    fixture = SimpleNamespace(parent=parent, root=root, foreign=foreign, donor=donor,
                              parent_fd=parent_fd, root_fd=root_fd, foreign_fd=foreign_fd,
                              donor_fd=donor_fd, view=view, mkdir=mkdir, directories=directories)
    try:
        yield fixture
    finally:
        for fd in directories:
            if os.fstat(fd).st_nlink:
                os.fchmod(fd, 0o700)
        for fd in reversed(handles):
            os.close(fd)


def assert_unaffected(fixture):
    assert (fixture.foreign / "sentinel").read_bytes() == b"foreign bytes"
    assert (fixture.donor / "sentinel").read_bytes() == b"donor bytes"
    assert (fixture.parent / "sibling" / "sentinel").read_bytes() == b"sibling bytes"
    assert os.fstat(fixture.parent_fd).st_ino == fixture.parent.stat().st_ino
    assert os.fstat(fixture.foreign_fd).st_ino == fixture.foreign.stat().st_ino
    assert os.fstat(fixture.donor_fd).st_ino == fixture.donor.stat().st_ino
    assert stat.S_IMODE(os.fstat(fixture.parent_fd).st_mode) == 0o700


def remove(fixture):
    return removal.remove_owned_tree(fixture.view, deadline_ns=time.monotonic_ns() + 20_000_000_000)


@pytest.mark.parametrize("layout", ["empty", "partial", "frozen", "outward_and_dangling_links"])
def test_actual_descriptor_primitive_removes_only_owned_tree(benign_tree, layout):
    fixture = benign_tree
    count = 0
    if layout in {"partial", "frozen"}:
        folder = fixture.mkdir("nested")
        (folder / "data").write_bytes(b"inert data")
        (fixture.root / "program-label").write_bytes(b"not executable runtime")
        (folder / "data").chmod(0o444 if layout == "frozen" else 0o600)
        (fixture.root / "program-label").chmod(0o555)
        count = 3
        if layout == "frozen":
            os.fchmod(fixture.directories[-1], 0o555)
            os.fchmod(fixture.root_fd, 0o555)
    elif layout == "outward_and_dangling_links":
        (fixture.root / "outward").symlink_to(fixture.foreign)
        (fixture.root / "dangling").symlink_to("../../missing")
        count = 2
    original = os.fstat(fixture.root_fd)
    summary = remove(fixture)
    assert summary.removed_entries == count and summary.root_unlinked is True
    assert fixture.view.used and not fixture.root.exists()
    detached = os.fstat(fixture.root_fd)
    assert (detached.st_dev, detached.st_ino, detached.st_nlink) == (original.st_dev, original.st_ino, 0)
    assert_unaffected(fixture)
    with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
        remove(fixture)


@pytest.mark.parametrize("fault", ["wrong_root_inode", "wrong_parent_inode", "wrong_root_mount", "wrong_parent_mount",
                                   "missing_name", "replacement_name", "symlink_name", "parent_mode", "root_mode"])
def test_anchor_or_name_refusal_precedes_permission_or_unlink(benign_tree, monkeypatch, fault):
    fixture = benign_tree
    (fixture.root / "retained").write_bytes(b"owned remainder")
    if fault.startswith("wrong_"):
        target = fixture.view.root_identity if "root" in fault else fixture.view.parent_identity
        target["mount_id" if fault.endswith("mount") else "inode"] += 1
    elif fault in {"missing_name", "replacement_name", "symlink_name"}:
        fixture.root.rename(fixture.parent / "moved-owned")
        if fault == "replacement_name":
            fixture.root.mkdir(mode=0o700)
            (fixture.root / "replacement").write_bytes(b"foreign replacement")
        elif fault == "symlink_name":
            fixture.root.symlink_to(fixture.foreign)
    elif fault == "parent_mode":
        os.fchmod(fixture.parent_fd, 0o755)
    else:
        os.fchmod(fixture.root_fd, 0o1777)
    mutations = []
    with pytest.MonkeyPatch.context() as patch:
        for name in ("fchmod", "unlink", "rmdir", "chmod"):
            patch.setattr(removal.os, name, lambda *args, operation=name, **kwargs: mutations.append(operation))
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
    assert mutations == []
    os.fchmod(fixture.parent_fd, 0o700)
    assert os.stat("retained", dir_fd=fixture.root_fd, follow_symlinks=False).st_size == len(b"owned remainder")
    assert_unaffected(fixture)


@pytest.mark.parametrize("fault", ["fifo", "hardlink_file", "hardlink_symlink", "setid", "sticky", "invalid_component"])
def test_preflight_anomalies_refuse_without_content_open_or_mutation(benign_tree, monkeypatch, fault):
    fixture = benign_tree
    target = fixture.root / "anomaly"
    if fault == "fifo":
        os.mkfifo(target, 0o600)
    elif fault == "hardlink_symlink":
        target.symlink_to(fixture.foreign)
        os.link(target, fixture.root / "alias", follow_symlinks=False)
    elif fault == "invalid_component":
        (fixture.root / "back\\slash").write_bytes(b"invalid")
    else:
        target.write_bytes(b"do not read me")
        if fault == "hardlink_file":
            os.link(target, fixture.root / "alias")
        elif fault == "setid":
            target.chmod(0o4600)
        else:
            target.chmod(0o1600)
    original_open = os.open
    mutation = []

    def no_content_open(path, flags, *args, **kwargs):
        if kwargs.get("dir_fd") is not None and str(path) in {"anomaly", "alias", "back\\slash"}:
            assert flags & os.O_PATH and flags & os.O_NOFOLLOW
        return original_open(path, flags, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(removal.os, "open", no_content_open)
        for name in ("fchmod", "unlink", "rmdir", "chmod"):
            patch.setattr(removal.os, name, lambda *args, operation=name, **kwargs: mutation.append(operation))
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
    assert mutation == [] and fixture.root.exists()
    assert_unaffected(fixture)


@pytest.mark.parametrize("depth,accepted", [(24, True), (25, False)])
def test_depth_boundary_is_exact_without_expanding_removal_scope(benign_tree, depth, accepted):
    fixture = benign_tree
    parts = []
    for index in range(depth):
        parts.append("d")
        fixture.mkdir("/".join(parts))
    if accepted:
        assert remove(fixture).removed_entries == depth
    else:
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
        assert (fixture.root / "/".join(parts)).is_dir()
    assert_unaffected(fixture)


@pytest.mark.parametrize("length,accepted", [(512, True), (513, False)])
def test_relative_path_utf8_byte_boundary_is_exact(benign_tree, length, accepted):
    fixture = benign_tree
    parts = ["a" * 127, "b" * 127, "c" * 127, "d" * (length - 384)]
    assert len("/".join(parts).encode()) == length
    for index in range(1, len(parts) + 1):
        fixture.mkdir("/".join(parts[:index]))
    if accepted:
        assert remove(fixture).removed_entries == 4
    else:
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
        assert fixture.root.exists()
    assert_unaffected(fixture)


@pytest.mark.parametrize("count,accepted", [(16_384, True), (16_385, False)])
def test_descendant_count_boundary_does_not_sort_or_delete_uncapped_entries(benign_tree, count, accepted):
    fixture = benign_tree
    for index in range(count):
        (fixture.root / f"leaf-{index}").write_bytes(b"")
    if accepted:
        assert remove(fixture).removed_entries == count
    else:
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
        assert (fixture.root / "leaf-0").exists() and (fixture.root / f"leaf-{count - 1}").exists()
    assert_unaffected(fixture)


def test_primitive_exact_deadline_refuses_before_first_mutation(benign_tree, monkeypatch):
    fixture = benign_tree
    (fixture.root / "retained").write_bytes(b"owned")
    mutations = []
    with pytest.MonkeyPatch.context() as patch:
        for name in ("fchmod", "unlink", "rmdir"):
            patch.setattr(removal.os, name, lambda *args, operation=name, **kwargs: mutations.append(operation))
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)) as error:
            removal.remove_owned_tree(fixture.view, deadline_ns=time.monotonic_ns())
    assert error.value.reason == "deadline_exceeded" and mutations == []
    assert (fixture.root / "retained").read_bytes() == b"owned"
    assert_unaffected(fixture)


@pytest.mark.parametrize("fault", ["same_device_bind", "mount_unavailable", "xattr_unavailable"])
def test_mount_or_xattr_fault_model_refuses_without_widening_scope(benign_tree, monkeypatch, fault):
    """Fault-injected metadata, expressly not an actual mounted-tree test."""
    fixture = benign_tree
    (fixture.root / "retained").write_bytes(b"owned")
    actual_mount = profile._mount_id
    actual_stat = os.fstat
    mutations = []

    def mount(fd, budget):
        info = actual_stat(fd)
        if info.st_ino == fixture.view.root_identity["inode"]:
            if fault == "mount_unavailable":
                raise OSError("modeled unsupported mount metadata")
            if fault == "same_device_bind":
                return actual_mount(fd, budget) + 1
        return actual_mount(fd, budget)

    def no_xattrs(*args, **kwargs):
        raise OSError("modeled unsupported security xattrs")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(profile, "_mount_id", mount)
        if fault == "xattr_unavailable":
            patch.setattr(os, "listxattr", no_xattrs)
        for name in ("fchmod", "unlink", "rmdir"):
            patch.setattr(removal.os, name, lambda *args, operation=name, **kwargs: mutations.append(operation))
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
    assert mutations == [] and (fixture.root / "retained").read_bytes() == b"owned"
    assert_unaffected(fixture)


def test_permissions_restore_only_checked_retained_directory_descriptors(benign_tree, monkeypatch):
    fixture = benign_tree
    nested = fixture.mkdir("nested")
    (nested / "leaf").write_bytes(b"frozen leaf")
    (nested / "leaf").chmod(0o444)
    for fd in fixture.directories:
        os.fchmod(fd, 0o555)
    expected_inodes = {os.fstat(fd).st_ino for fd in fixture.directories}
    original_chmod = os.fchmod
    changed = []

    def checked_chmod(fd, mode):
        info = os.fstat(fd)
        assert stat.S_ISDIR(info.st_mode) and info.st_ino in expected_inodes
        assert mode == 0o700 and fd != fixture.parent_fd
        changed.append(info.st_ino)
        return original_chmod(fd, mode)

    def pathname_chmod_forbidden(*args, **kwargs):
        raise AssertionError("removal used pathname chmod")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(removal.os, "fchmod", checked_chmod)
        patch.setattr(removal.os, "chmod", pathname_chmod_forbidden)
        assert remove(fixture).removed_entries == 2
    assert set(changed) == expected_inodes and len(changed) == 2
    assert_unaffected(fixture)


def test_root_name_move_after_first_chmod_stops_before_any_leaf_deletion(benign_tree, monkeypatch):
    fixture = benign_tree
    (fixture.root / "retained").write_bytes(b"owned remainder")
    os.fchmod(fixture.root_fd, 0o555)
    original_chmod = os.fchmod
    mutated = []
    root_inode = os.fstat(fixture.root_fd).st_ino

    def move_after_chmod(fd, mode):
        original_chmod(fd, mode)
        if os.fstat(fd).st_ino == root_inode:
            fixture.root.rename(fixture.parent / "moved-owned")
            fixture.root.mkdir(mode=0o700)
            (fixture.root / "replacement").write_bytes(b"foreign replacement")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(removal.os, "fchmod", move_after_chmod)
        for name in ("unlink", "rmdir"):
            patch.setattr(removal.os, name, lambda *args, operation=name, **kwargs: mutated.append(operation))
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
    assert mutated == []
    assert (fixture.parent / "moved-owned" / "retained").read_bytes() == b"owned remainder"
    assert (fixture.root / "replacement").read_bytes() == b"foreign replacement"
    assert_unaffected(fixture)


def test_mid_unlink_failure_retains_partial_remainder_without_recreating_deleted_leaf(benign_tree, monkeypatch):
    fixture = benign_tree
    for name in ("first", "second"):
        (fixture.root / name).write_bytes(name.encode())
    original_unlink = os.unlink
    removed = []

    def fail_second(name, *, dir_fd):
        if removed:
            raise OSError("modeled EIO after a successful unlink")
        original_unlink(name, dir_fd=dir_fd)
        removed.append(name)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(removal.os, "unlink", fail_second)
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
    assert len(removed) == 1 and not (fixture.root / removed[0]).exists()
    retained = ({"first", "second"} - set(removed)).pop()
    assert (fixture.root / retained).read_bytes() == retained.encode()
    assert fixture.root.exists() and os.fstat(fixture.root_fd).st_nlink > 0
    assert_unaffected(fixture)


def test_uncertain_final_rmdir_never_becomes_success_from_absence_on_retry(benign_tree, monkeypatch):
    fixture = benign_tree
    original_rmdir = os.rmdir

    def lost_result(name, *, dir_fd):
        original_rmdir(name, dir_fd=dir_fd)
        if dir_fd == fixture.parent_fd:
            raise OSError("modeled lost post-rmdir outcome")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(removal.os, "rmdir", lost_result)
        with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
            remove(fixture)
    assert not fixture.root.exists() and os.fstat(fixture.root_fd).st_nlink == 0
    retry = removal.RemovalRootView(fixture.parent_fd, fixture.root_fd, ALLOCATION,
                                   fixture.view.parent_identity, fixture.view.root_identity)
    with pytest.raises((removal.RemovalRefused, profile.ProfileRefused, OSError)):
        removal.remove_owned_tree(retry, deadline_ns=time.monotonic_ns() + 20_000_000_000)
    assert_unaffected(fixture)


@pytest.fixture
def debt_model(monkeypatch):
    """Private provenance is synthetic and makes no kernel ownership claim."""
    lane = capture.CaptureLane()
    allocation = profile.OwnedAllocation("capture-" + ALLOCATION, 701, 702, **ROOT,
                                         parent_identity=tuple(PARENT.values()), boot_nonce="d" * 64)
    identity = capture.ProcessIdentity(41, 700, 42, 43, 40, "/immutable/model/usr/bin/python3.12",
                                       ("fixed", "-I", "-S", "-B"), "e" * 64)
    process = capture.OwnedProcess(41, 604, identity, confirmed_exit=True, exit_code=70)
    quarantine = capture.CaptureQuarantine(lane, allocation, process, None, "capture_integrity_failed")
    lane.occupant = quarantine
    capture._record_quarantine(quarantine, writer_attempted=True,
                               original_job_deadline_ns=600_000_000_000, origin="capture_failure")
    state = SimpleNamespace(q=quarantine, lane=lane, allocation=allocation, process=process,
                            closed=[], signals=[], clock=SimpleNamespace(now=100_000_000_000))

    def forbidden(*args, **kwargs):
        raise AssertionError("metadata ownership operation performed external IO")

    monkeypatch.setattr(removal.time, "monotonic_ns", lambda: state.clock.now)
    monkeypatch.setattr(removal.os, "close", state.closed.append)
    monkeypatch.setattr(removal.signal, "pidfd_send_signal", lambda fd, sig: state.signals.append((fd, sig)))
    for name in ("open", "stat", "fstat", "scandir", "unlink", "rmdir", "fchmod", "posix_spawn", "kill", "waitpid"):
        monkeypatch.setattr(removal.os, name, forbidden)
    monkeypatch.setattr(removal.time, "sleep", forbidden)
    return state


@pytest.mark.parametrize("fault", ["reconstructed", "allocation_copy", "process_copy", "forgot_process", "unknown_spawn",
                                   "lost_identity", "no_pidfd", "no_exit", "boot_nonce", "parent_identity",
                                   "root_inode", "root_mount", "allocation_name", "root_fd", "lane"])
def test_live_authority_gate_refuses_reconstruction_and_changed_originals(debt_model, fault):
    model = debt_model
    q = model.q
    if fault == "reconstructed":
        q._provenance = None
    elif fault == "allocation_copy":
        q.allocation = replace(q.allocation)
    elif fault == "process_copy":
        q.process = replace(q.process)
    elif fault == "forgot_process":
        q.process = None
    elif fault == "unknown_spawn":
        q.process.pid = -1
        q.process.identity = None
    elif fault == "lost_identity":
        q.process.identity_lost = True
    elif fault == "no_pidfd":
        q.process.pidfd = -1
    elif fault == "no_exit":
        q.process.confirmed_exit = False
    elif fault == "boot_nonce":
        q.allocation.boot_nonce = "f" * 64
    elif fault == "parent_identity":
        q.allocation.parent_identity = (11, 23, 13)
    elif fault in {"root_inode", "root_mount", "root_fd"}:
        attr = {"root_inode": "inode", "root_mount": "mount_id", "root_fd": "root_fd"}[fault]
        setattr(q.allocation, attr, getattr(q.allocation, attr) + 1)
    elif fault == "allocation_name":
        q.allocation.allocation_name = "capture-" + "f" * 32
    else:
        q.lane.occupant = object()
    occupant = q.lane.occupant
    with pytest.raises(capture.CaptureRefused):
        capture._removal_authority(q)
    assert model.closed == model.signals == [] and q.lane.occupant is occupant


@pytest.mark.parametrize("extra,accepted", [(0, True), (1, False)])
def test_metadata_retention_cap_is_checked_before_append(monkeypatch, extra, accepted):
    """Enumeration fault model; exact 8 MiB accounting, no real directory IO."""
    class Scan:
        def __enter__(self):
            return iter([SimpleNamespace(name="leaf")])

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(removal.os, "scandir", lambda fd: Scan())
    monkeypatch.setattr(removal.time, "monotonic_ns", lambda: 100)
    cost = 384 + 4 * len("leaf".encode())
    counters = [0, 8 * 1024 * 1024 - cost + extra, 0]
    before = list(counters)
    if accepted:
        assert removal._enumerate(701, (), removal._Budget(200), counters) == ["leaf"]
        assert counters[:2] == [1, 8 * 1024 * 1024]
    else:
        with pytest.raises(removal.RemovalRefused) as error:
            removal._enumerate(701, (), removal._Budget(200), counters)
        assert error.value.reason == "limit_exceeded" and counters == before


@pytest.mark.parametrize("original_deadline", [None, 90_000_000_000])
def test_initial_generation_zero_transfer_preserves_real_capture_debt(debt_model, monkeypatch, original_deadline):
    model = debt_model
    # This private acquisition fixture explicitly models an expired slot or an
    # admitted capture failure; it does not fabricate a historical remover.
    q = capture.CaptureQuarantine(model.lane, model.allocation, model.process, None, "deadline_exceeded")
    model.lane.occupant = q
    capture._record_quarantine(q, writer_attempted=True, original_job_deadline_ns=original_deadline,
                               origin="expired_slot" if original_deadline is None else "capture_failure")
    monkeypatch.setattr(removal.threading, "active_count", lambda: 1)
    holder = removal.RemovalDebtHolder(model.lane)
    permit = removal.transfer_removal_debt(q, None, holder)
    assert permit.quarantine is q and permit.recipient is holder and permit.generation == 1
    assert not permit.consumed and holder.entry is q and holder.permit is permit
    assert q.removal_generation == 1 and q._removal_claim is None and q._removal_owner is holder
    assert q._provenance.original_job_deadline_ns == original_deadline
    assert not any(isinstance(item, removal.RemovalClaim) for item in q._removal_history)
    assert model.lane.occupant is q and (model.allocation.root_fd, model.allocation.parent_fd) == (701, 702)
    with pytest.raises(removal.RemovalRefused):
        removal.transfer_removal_debt(q, None, holder)
    assert q.removal_generation == 1 and holder.permit is permit
    assert model.closed == model.signals == []


def test_initial_transfer_allows_only_recorded_no_writer_not_lost_writer(debt_model, monkeypatch):
    model = debt_model
    q = capture.CaptureQuarantine(model.lane, model.allocation, None, None, "deadline_exceeded")
    model.lane.occupant = q
    capture._record_quarantine(q, writer_attempted=False, original_job_deadline_ns=None, origin="preparation_failure")
    monkeypatch.setattr(removal.threading, "active_count", lambda: 1)
    permit = removal.transfer_removal_debt(q, None, removal.RemovalDebtHolder(model.lane))
    assert permit.generation == 1 and q.process is None
    assert model.closed == model.signals == []


def job_claim(model):
    timing = removal.RemovalTiming("job", "1" * 32, 600_000_000_000, 600_000_000_000)
    return removal._claim(model.q, timing, model.clock.now)


def failed_claim(model, *, attempted=False, confirmed=True):
    claim = job_claim(model)
    claim.reason = "deadline_exceeded"
    claim.state = "quarantined" if confirmed else "quarantined_pending_io"
    claim.spawn_attempted = attempted
    if attempted:
        identity = capture.ProcessIdentity(51, 800, 42, 43, 40, "/immutable/removal/usr/bin/python3.12",
                                           ("fixed", "-I", "-S", "-B"), "f" * 64)
        claim.process = capture.OwnedProcess(51, 614, identity, confirmed_exit=confirmed,
                                            exit_code=70 if confirmed else None)
        removal._record_process(claim)
    return claim


@pytest.mark.parametrize("attempted", [False, True])
def test_failed_claim_transfer_retires_exact_owner_and_grants_one_attempt(debt_model, monkeypatch, attempted):
    model = debt_model
    monkeypatch.setattr(removal.threading, "active_count", lambda: 1)
    old = failed_claim(model, attempted=attempted)
    old_deadline, old_process = old.attempt_deadline_ns, old.process
    holder = removal.RemovalDebtHolder(model.lane)
    permit = removal.transfer_removal_debt(model.q, old, holder)
    assert old.retired and old.reason == "deadline_exceeded" and old.process is old_process
    assert old.attempt_deadline_ns == old_deadline and old in model.q._removal_history
    assert model.q.removal_generation == 1 and model.q._removal_claim is None
    timing = removal.RemovalTiming("maintenance", "2" * 32, model.clock.now + 20_000_000_000,
                                   600_000_000_000, permit)
    new = removal._claim(model.q, timing, model.clock.now)
    assert new is model.q._removal_claim and new is not old and new.generation == 1
    assert permit.consumed and new.process is None and not new.spawn_attempted
    for operation in (lambda: removal._check(old),
                      lambda: removal.transfer_removal_debt(model.q, old, holder),
                      lambda: removal.transfer_removal_debt(model.q, None, holder),
                      lambda: removal._claim(model.q, timing, model.clock.now)):
        with pytest.raises(removal.RemovalRefused):
            operation()
    assert model.q._removal_claim is new and model.q.removal_generation == 1
    assert model.q.process is model.process and model.lane.occupant is model.q
    assert model.closed == model.signals == []


@pytest.mark.parametrize("fault", ["unknown_spawn", "pending_io", "lost_identity", "missing_pidfd", "wrong_pid"])
def test_failed_remover_without_qualified_exit_cannot_rearm(debt_model, monkeypatch, fault):
    model = debt_model
    monkeypatch.setattr(removal.threading, "active_count", lambda: 1)
    old = failed_claim(model, attempted=True, confirmed=False)
    if fault == "unknown_spawn":
        old.process = capture.OwnedProcess(-1)
    elif fault == "lost_identity":
        old.process.confirmed_exit = True
        old.process.identity_lost = True
    elif fault == "missing_pidfd":
        old.process.confirmed_exit = True
        old.process.pidfd = -1
    elif fault == "wrong_pid":
        old.process.confirmed_exit = True
        old.process.pid += 1
    holder = removal.RemovalDebtHolder(model.lane)
    with pytest.raises(removal.RemovalRefused):
        removal.transfer_removal_debt(model.q, old, holder)
    assert holder.entry is None and holder.permit is None
    assert model.q.removal_generation == 0 and model.q._removal_claim is old and not old.retired
    assert model.q._removal_owner is None and model.lane.occupant is model.q
    assert model.closed == model.signals == []


@pytest.mark.parametrize("fault", ["capacity", "wrong_lane", "not_quiescent", "threads", "overflow", "copy_claim", "none_bypass"])
def test_failed_acknowledgment_is_atomic_and_keeps_original_claim(debt_model, monkeypatch, fault):
    model = debt_model
    monkeypatch.setattr(removal.threading, "active_count", lambda: 1)
    old = failed_claim(model)
    holder = removal.RemovalDebtHolder(model.lane)
    expected = old
    if fault == "capacity":
        holder.entry = object()
    elif fault == "wrong_lane":
        holder.lane = capture.CaptureLane()
    elif fault == "not_quiescent":
        holder.quiescent = False
    elif fault == "threads":
        monkeypatch.setattr(removal.threading, "active_count", lambda: 2)
    elif fault == "overflow":
        model.q.removal_generation = 2**64 - 1
        old.generation = 2**64 - 1
    elif fault == "copy_claim":
        expected = replace(old)
    else:
        expected = None
    before = (model.q.removal_generation, model.q._removal_claim, model.q._removal_owner,
              holder.entry, holder.permit, tuple(model.q._removal_history))
    with pytest.raises(removal.RemovalRefused):
        removal.transfer_removal_debt(model.q, expected, holder)
    after = (model.q.removal_generation, model.q._removal_claim, model.q._removal_owner,
             holder.entry, holder.permit, tuple(model.q._removal_history))
    assert after == before and not old.retired
    assert model.lane.occupant is model.q and model.closed == model.signals == []


@pytest.fixture
def run_model(debt_model, monkeypatch):
    model = debt_model
    claim = job_claim(model)
    identity = capture.ProcessIdentity(51, 800, 42, 43, 40, "/immutable/removal/usr/bin/python3.12",
                                       ("fixed", "-I", "-S", "-B"), "f" * 64)
    process = capture.OwnedProcess(51, 614, identity)
    channel = DatagramModel()
    # No runtime verification is called: these owner pins are synthetic labels.
    binding = removal.RemovalRuntimeBinding(removal.RUNTIME_SCHEMA, *["c" * 64] * 7)
    owner = removal.RemovalOwnerInputs(601, "/immutable/removal", binding, b"synthetic", True, True)
    prepared = removal.PreparedRemoval(claim, owner, NONCE, "f" * 64, process, channel, 705, 706,
                                        prepared_at_ns=model.clock.now, rx_seq=2)
    claim.process, claim.prepared, claim.spawn_attempted, claim.state = process, prepared, True, "prepared"
    removal._record_process(claim)
    claim.held_fds[:] = [705, 706, 707]
    model.claim, model.prepared, model.remover, model.channel = claim, prepared, process, channel
    model.logs, model.reads, model.wait_calls = {705: [], 706: []}, [], []
    model.exit_ready, model.exit_code, model.wait_results = False, 0, None

    def ready(readers, writers, errors, timeout):
        assert timeout == 0
        return [fd for fd in readers if (fd is channel and channel.packets)
                or (isinstance(fd, int) and fd in model.logs and model.logs[fd])
                or (fd == 614 and model.exit_ready)], [], []

    def waitid(kind, fd, options):
        assert kind == os.P_PIDFD and fd == 614
        assert options & os.WNOHANG and options & os.WEXITED
        model.wait_calls.append(options)
        if model.wait_results is not None:
            return model.wait_results.pop(0)
        return SimpleNamespace(si_pid=51, si_code=os.CLD_EXITED, si_status=model.exit_code)

    def read(fd, count):
        assert fd in model.logs
        model.reads.append((fd, count))
        if not model.logs[fd]:
            raise BlockingIOError()
        raw = model.logs[fd].pop(0)
        assert len(raw) <= count
        return raw

    monkeypatch.setattr(removal.select, "select", ready)
    monkeypatch.setattr(removal.os, "waitid", waitid)
    monkeypatch.setattr(removal.os, "read", read)
    monkeypatch.setattr(removal.threading, "active_count", lambda: 1)
    return model


def queue_complete(model, *, seq=2, value=None):
    raw = removal.encode_frame("COMPLETE", NONCE, seq, payload("COMPLETE") if value is None else value)
    model.channel.packets.append((raw, [credentials((51, 42, 43))], 0, None))


def queue_end(model):
    model.channel.packets.append((b"", [], 0, None))
    model.logs[705].append(b"")
    model.logs[706].append(b"")


def test_begin_never_refreshes_preparation_budget_and_is_single_use(run_model):
    model = run_model
    deadline = model.claim.attempt_deadline_ns
    model.clock.now += 7_000_000_000
    run = removal.begin_removal(model.prepared)
    frame = removal.decode_frame(model.channel.sent[0], nonce=NONCE, seq=1)
    assert frame["payload"] == {"removal_deadline_ns": deadline, "deadline_ceiling_ns": 600_000_000_000}
    assert deadline == 120_000_000_000 and model.prepared.used and run.reason is None
    with pytest.raises(removal.RemovalRefused):
        removal.begin_removal(model.prepared)
    assert len(model.channel.sent) == 1 and model.closed == []
    assert model.lane.occupant is model.q and model.q.process is model.process


@pytest.mark.parametrize("fault", ["expired", "short_send", "unknown_send", "lost_identity"])
def test_begin_interruption_never_reuses_prepared_writer(run_model, fault):
    model = run_model
    if fault == "expired":
        model.clock.now = model.claim.attempt_deadline_ns
    elif fault == "short_send":
        model.channel.send_fault = 0
    elif fault == "unknown_send":
        model.channel.send_fault = OSError("modeled uncertain BEGIN delivery")
    else:
        model.remover.identity_lost = True
    run = removal.begin_removal(model.prepared)
    assert run.reason is not None and model.prepared.used
    assert len(model.channel.sent) == (1 if fault in {"short_send", "unknown_send"} else 0)
    with pytest.raises(removal.RemovalRefused):
        removal.begin_removal(model.prepared)
    assert model.closed == [] and model.lane.occupant is model.q


def test_complete_is_provisional_until_matching_reap_eofs_and_one_terminal_release(run_model):
    model = run_model
    run = removal.begin_removal(model.prepared)
    queue_complete(model)
    assert run.poll(model.clock.now).state == "completion_pending_exit"
    assert model.claim.qualified is None and model.closed == []
    queue_end(model)
    assert run.poll(model.clock.now).state == "completion_pending_exit"
    model.exit_ready = True
    assert run.poll(model.clock.now).state == "removed"
    assert model.wait_calls == [os.WEXITED | os.WNOHANG | os.WNOWAIT, os.WEXITED | os.WNOHANG]
    assert model.closed == [] and model.lane.occupant is model.q
    assert run.take_disposition().state == "removed"
    assert model.closed == [701, 702, 604, 705, 706, 707, 614]
    assert model.channel.closed and model.lane.occupant is None
    assert model.allocation.root_fd == model.allocation.parent_fd == -1
    assert model.q.process is model.process and model.process.pidfd == -1
    next_owner = object()
    model.lane.occupant = next_owner
    assert capture.request_cleanup(model.q).state == "removed"
    with pytest.raises(removal.RemovalRefused):
        run.take_disposition()
    assert model.lane.occupant is next_owner and model.closed.count(604) == 1


@pytest.mark.parametrize("fault", ["no_report", "nonzero_exit", "duplicate", "wrong_parent", "early_eof", "late",
                                   "wrong_reap_pid", "lost_identity_idle", "missing_log_eof"])
def test_report_exit_or_mutable_status_cannot_forge_terminal_removal(run_model, fault):
    model = run_model
    run = removal.begin_removal(model.prepared)
    if fault not in {"no_report", "early_eof", "lost_identity_idle"}:
        value = payload("COMPLETE")
        if fault == "wrong_parent":
            value["parent_identity"]["inode"] += 1
        queue_complete(model, value=value)
        if fault == "duplicate":
            queue_complete(model, seq=3)
    if fault != "lost_identity_idle":
        queue_end(model)
        if fault == "missing_log_eof":
            model.logs[706].clear()
        model.exit_ready = True
    if fault == "nonzero_exit":
        model.exit_code = 70
    elif fault == "wrong_reap_pid":
        model.wait_results = [SimpleNamespace(si_pid=99, si_code=os.CLD_EXITED, si_status=0)]
    elif fault == "lost_identity_idle":
        model.remover.identity_lost = True
    elif fault == "late":
        model.clock.now = model.claim.attempt_deadline_ns
    run.poll(model.clock.now)
    if fault == "missing_log_eof":
        assert run.reason is None and model.claim.qualified is None
        model.clock.now = model.claim.attempt_deadline_ns
        run.poll(model.clock.now)
    assert run.reason is not None and model.claim.qualified is None
    assert model.closed == [] and model.lane.occupant is model.q
    assert model.allocation.root_fd == 701 and model.allocation.parent_fd == 702


@pytest.mark.parametrize("fault", ["claim", "generation", "lane", "process", "prepared"])
def test_stale_run_refuses_before_send_signal_or_state_mutation(run_model, fault):
    model = run_model
    run = removal.begin_removal(model.prepared)
    if fault == "claim":
        model.q._removal_claim = replace(model.claim)
    elif fault == "generation":
        model.q.removal_generation += 1
    elif fault == "lane":
        model.lane.occupant = object()
    elif fault == "process":
        model.claim.process = replace(model.remover)
    else:
        model.claim.prepared = replace(model.prepared)
    occupant, sent = model.lane.occupant, list(model.channel.sent)
    for operation in (lambda: run.poll(model.clock.now), lambda: run.request_cancel(model.clock.now), run.take_disposition):
        with pytest.raises(removal.RemovalRefused):
            operation()
    assert run.reason is None and run.state == "removing"
    assert model.closed == model.signals == [] and model.channel.sent == sent
    assert model.lane.occupant is occupant


def test_cancel_truncates_grace_retains_pending_io_and_never_promotes_late_exit(run_model):
    model = run_model
    run = removal.begin_removal(model.prepared)
    queue_complete(model)
    run.poll(model.clock.now)
    model.clock.now = model.claim.attempt_deadline_ns - 1_000_000_000
    run.request_cancel(model.clock.now)
    run.request_cancel(model.clock.now)
    assert not run.complete and model.claim.qualified is None
    assert run.term_until_ns == run.exit_until_ns == model.claim.attempt_deadline_ns
    model.clock.now = model.claim.attempt_deadline_ns
    assert run.poll(model.clock.now).to_record() == {
        "state": "quarantined_pending_io", "reason": "cancelled", "kill_action": "kill-failed"}
    assert model.signals == [(614, signal.SIGTERM), (614, signal.SIGKILL)]
    holder = removal.RemovalDebtHolder(model.lane)
    with pytest.raises(removal.RemovalRefused):
        removal.transfer_removal_debt(model.q, model.claim, holder)
    assert model.q.removal_generation == 0 and holder.entry is None
    model.exit_ready = True
    assert run.poll(model.clock.now).state == "quarantined"
    assert run.take_disposition().state == "cleanup_incomplete"
    assert model.closed == [] and model.lane.occupant is model.q
    assert removal.transfer_removal_debt(model.q, model.claim, holder).generation == 1


def test_poll_schedules_at_most_sixteen_events_and_sixty_four_kib(run_model):
    model = run_model
    run = removal.begin_removal(model.prepared)
    for _ in range(100):
        model.channel.packets.append((b"x" * 4097, [], socket.MSG_TRUNC, None))
        model.logs[705].append(b"x" * 4096)
        model.logs[706].append(b"x" * 4096)
    run.poll(model.clock.now)
    assert 0 < model.channel.received + len(model.reads) <= 16
    assert model.channel.received * 4097 + sum(count for _, count in model.reads) <= 65536
    assert model.channel.packets and model.logs[705] and model.logs[706]
    assert model.closed == [] and model.lane.occupant is model.q


@pytest.mark.parametrize("prior_stream_bytes", [0, 1024 * 1024 + 1])
def test_poll_charges_full_diagnostic_reads_even_when_overflow_raises(run_model, prior_stream_bytes):
    """M1 paired normal/overflow fault model; no real reads or process proof.

    Readiness orders malformed control, stdout, stderr. Without pre-read debit,
    sixteen events can return6*4097 +10*4096 =65,542 bytes after log overflow.
    The paired zero-counter case follows the same schedule without log errors.
    """
    model = run_model
    run = removal.begin_removal(model.prepared)
    run.request_cancel(model.clock.now, "cancelled")
    original = (run.reason, run.cancel_at_ns, run.term_until_ns, run.exit_until_ns,
                model.claim.reason, model.claim.attempt_deadline_ns)
    model.prepared.log_bytes[:] = [prior_stream_bytes, prior_stream_bytes]
    for _ in range(100):
        model.channel.packets.append((b"x" * 4097, [], socket.MSG_TRUNC, None))
        model.logs[705].append(b"x" * 4096)
        model.logs[706].append(b"x" * 4096)
    for _ in range(2):
        received_before = model.channel.received
        reads_before = len(model.reads)
        diagnostic_before = tuple(model.prepared.log_bytes)
        update = run.poll(model.clock.now)
        # The datagram model always returns4,097 payload bytes. Log counters
        # include bytes actually returned, including the reads which raise.
        control_bytes = (model.channel.received - received_before) * 4097
        diagnostic_bytes = sum(after - before for after, before in
                               zip(model.prepared.log_bytes, diagnostic_before))
        actual_bytes = control_bytes + diagnostic_bytes
        assert 0 < actual_bytes <= 65_536
        assert 0 < model.channel.received - received_before + len(model.reads) - reads_before <= 16
        assert all(after > before for after, before in zip(model.prepared.log_bytes, diagnostic_before))
        assert {fd for fd, _ in model.reads[reads_before:]} == {705, 706}
        assert all(count == 4096 for _, count in model.reads[reads_before:])
        assert update.to_record() == {"state": "terminating"}
        assert (run.reason, run.cancel_at_ns, run.term_until_ns, run.exit_until_ns,
                model.claim.reason, model.claim.attempt_deadline_ns) == original
        assert model.signals == [(614, signal.SIGTERM)]
        assert model.closed == [] and not model.channel.closed
        assert model.lane.occupant is model.q and model.q._removal_claim is model.claim
        assert (model.allocation.root_fd, model.allocation.parent_fd) == (701, 702)
    assert model.channel.packets and model.logs[705] and model.logs[706]


def test_poll_five_millisecond_scheduling_cap_does_not_drain_model(run_model, monkeypatch):
    model = run_model
    run = removal.begin_removal(model.prepared)
    model.logs[705].extend([b"x"] * 100)
    ticks = iter([model.clock.now] * 4 + [model.clock.now + 5_000_000])
    monkeypatch.setattr(removal.time, "monotonic_ns", lambda: next(ticks, model.clock.now + 5_000_000))
    run.poll(model.clock.now)
    assert len(model.reads) <= 1 and len(model.logs[705]) >= 99
    assert model.closed == []


@pytest.mark.parametrize("stream", [705, 706])
def test_log_cap_counts_discarded_bytes_before_terminal_qualification(run_model, stream):
    model = run_model
    run = removal.begin_removal(model.prepared)
    model.prepared.log_bytes[stream - 705] = 1024 * 1024
    model.logs[stream].append(b"x")
    run.poll(model.clock.now)
    assert run.reason == "limit_exceeded" and model.claim.qualified is None
    assert model.closed == [] and model.lane.occupant is model.q


@pytest.mark.parametrize("fault", ["mutable_state", "lost_exit", "identity_copy", "missing_eof", "late_take"])
def test_finalization_rechecks_exact_qualified_proof_before_any_close(run_model, fault):
    model = run_model
    run = removal.begin_removal(model.prepared)
    if fault == "mutable_state":
        run.state, run.complete = "removed", True
        run.summary = removal.RemovalSummary(3)
        model.remover.confirmed_exit, model.remover.exit_code = True, 0
        model.prepared.eof[:] = [True, True, True]
    else:
        queue_complete(model)
        queue_end(model)
        model.exit_ready = True
        assert run.poll(model.clock.now).state == "removed"
        if fault == "lost_exit":
            model.remover.confirmed_exit = False
        elif fault == "identity_copy":
            model.remover.identity = replace(model.remover.identity)
        elif fault == "missing_eof":
            model.prepared.eof[2] = False
        else:
            model.clock.now = model.claim.attempt_deadline_ns
    with pytest.raises(removal.RemovalRefused):
        run.take_disposition()
    assert model.closed == [] and model.lane.occupant is model.q
    assert model.q._removal_terminal is None
    if fault != "identity_copy":
        assert run.reason is not None


@pytest.mark.parametrize("fault", ["untrusted_domain", "expired_ceiling"])
def test_preparation_failure_claims_before_io_and_preserves_original_debt(debt_model, monkeypatch, fault):
    model = debt_model
    monkeypatch.setattr(removal.threading, "active_count", lambda: 1)
    owner = removal.RemovalOwnerInputs(601, "/immutable/removal", None, b"synthetic", fault != "untrusted_domain", True)
    timing = removal.RemovalTiming("job", "1" * 32, 600_000_000_000, 600_000_000_000)
    if fault == "expired_ceiling":
        model.clock.now = 600_000_000_000
    failure = removal.prepare_removal(model.q, owner, timing)
    assert isinstance(failure, removal.RemovalPreparationFailure)
    claim = failure.claim
    assert claim is model.q._removal_claim and claim.process is None and not claim.spawn_attempted
    assert failure.reason == ("supervisor_domain_unavailable" if fault == "untrusted_domain" else "deadline_exceeded")
    assert model.closed == model.signals == [] and model.lane.occupant is model.q
    with pytest.raises(removal.RemovalRefused):
        removal.prepare_removal(model.q, owner, timing)


def test_removal_source_keeps_two_bounded_metadata_passes_and_no_content_reads():
    """AST scope guard only; it cannot establish no-follow kernel behavior."""
    source = Path(removal.__file__).read_text()
    tree = ast.parse(source)
    primitive = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "remove_owned_tree")
    scans = [node for node in ast.walk(primitive) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "scan"
             and len(node.args) == 3 and isinstance(node.args[2], ast.Constant)]
    assert [call.args[2].value for call in scans] == [False, True]
    calls = [node for node in ast.walk(primitive) if isinstance(node, ast.Call)]
    assert not any(isinstance(node.func, ast.Attribute) and node.func.attr in
                   {"read", "readlink", "listdir", "rmtree", "glob", "rglob", "chdir", "chmod", "chown"}
                   for node in calls)
    assert removal.MAX_ENTRIES == 16_384 and removal.MAX_METADATA == 8 * 1024 * 1024
    assert profile.MAX_DEPTH == 24 and profile.MAX_PATH_BYTES == 512
    # Each of the two bounded scans admits at most16,384 descendants; guard
    # re-pins and final empty checks are separate depth-bounded metadata work.


def test_fixed_entry_source_orders_begin_before_primitive_and_keeps_six_fd_layout():
    """Text/AST ordering specification only, never bootstrap qualification."""
    source = Path(removal.__file__).with_name("native_removal_entry.py").read_text()
    tree = ast.parse(source)
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    begin = next(node for node in ast.walk(main) if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "begin" for target in node.targets))
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]
    primitives = [node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "remove_owned_tree"]
    assert len(primitives) == 1 and primitives[0].lineno > begin.lineno
    forbidden = {"capture_into_owned", "capture_private", "run_manifest", "fork", "posix_spawn", "subprocess", "Thread"}
    assert not any(isinstance(node.func, ast.Attribute) and node.func.attr in forbidden for node in calls)
    assert "sorted(existing) != list(range(6))" in source
    assert "RemovalRootView(4, 5," in source
    for limit in ("(resource.RLIMIT_CORE, 0)", "(resource.RLIMIT_NOFILE, 128)",
                  "(resource.RLIMIT_FSIZE, 0)", "(resource.RLIMIT_AS, 2 * 1024**3)",
                  "(resource.RLIMIT_CPU, 20)", "(resource.RLIMIT_NPROC, 32)"):
        assert limit in source
