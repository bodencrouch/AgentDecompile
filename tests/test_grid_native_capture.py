"""Authored Task11.6b regressions; NOT executed or collected in this packet.

Model tests call real public supervisor/codec APIs with explicit transport,
clock, select, waitid and pidfd fault models. Their synthetic process identity
is NOT OS identity/credential/cancellation qualification. The separate benign
filesystem fixture calls the real allocation/copy/rehash/freeze primitive;
even a future pass would establish neither helper execution nor a usable
CPython/objdiff runtime. No installation or subprocess fixture is provided.
"""
from __future__ import annotations

import array
import ast
import hashlib
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


NONCE = "a" * 64
ROOT = {"device": 11, "inode": 12, "mount_id": 13}
ALLOCATION = "b" * 32


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def payload(kind):
    ready = dict(allocation_id=ALLOCATION, root_identity=dict(ROOT),
                 profile_sha256="c" * 64, inventory_sha256="d" * 64)
    return {
        "CHALLENGE": dict(**ready, profile_id=profile.PROFILE_ID, helper_runtime_sha256="e" * 64),
        "HELLO": {"helper_runtime_sha256": "e" * 64},
        "READY": ready,
        "BEGIN": {"capture_deadline_ns": 100, "absolute_deadline_ns": 610},
        "COMPLETE": dict(**ready, entry_count=1, total_file_bytes=4),
        "ERROR": {"reason": "capture_integrity_failed", "detail": "copy refused"},
    }[kind]


@pytest.mark.parametrize("kind", ["CHALLENGE", "HELLO", "READY", "BEGIN", "COMPLETE", "ERROR"])
def test_codec_exact_canonical_positive(kind):
    raw = capture.encode_frame(kind, NONCE, 0, payload(kind))
    frame = capture.decode_frame(raw, nonce=NONCE, seq=0)
    assert frame == dict(schema=capture.SCHEMA, kind=kind, nonce=NONCE, seq=0, payload=payload(kind))
    assert raw == canonical(frame)


@pytest.mark.parametrize("mutation", ["nonce", "replay", "bool_seq", "negative_seq", "overflow_seq",
                                       "unknown_envelope", "missing_envelope", "unknown_payload", "missing_payload",
                                       "bool_root", "negative_root", "allocation_path", "upper_digest", "other_schema",
                                       "other_kind", "float_seq"])
def test_codec_rejects_altered_binding_or_shape(mutation):
    frame = dict(schema=capture.SCHEMA, kind="READY", nonce=NONCE, seq=1, payload=payload("READY"))
    if mutation == "nonce":
        frame["nonce"] = "f" * 64
    elif mutation == "replay":
        frame["seq"] = 0
    elif mutation in {"bool_seq", "negative_seq", "overflow_seq", "float_seq"}:
        frame["seq"] = {"bool_seq": True, "negative_seq": -1, "overflow_seq": 2**64, "float_seq": 1.0}[mutation]
    elif mutation == "unknown_envelope":
        frame["fd"] = 701
    elif mutation == "missing_envelope":
        del frame["nonce"]
    elif mutation == "unknown_payload":
        frame["payload"]["root_fd"] = 701
    elif mutation == "missing_payload":
        del frame["payload"]["allocation_id"]
    elif mutation in {"bool_root", "negative_root"}:
        frame["payload"]["root_identity"]["inode"] = True if mutation == "bool_root" else -1
    elif mutation == "allocation_path":
        frame["payload"]["allocation_id"] = "../foreign"
    elif mutation == "upper_digest":
        frame["payload"]["profile_sha256"] = "C" * 64
    elif mutation == "other_schema":
        frame["schema"] = "agentdecompile.native-region-ipc.v1"
    else:
        frame["kind"] = "START"
    with pytest.raises(capture.CaptureRefused) as error:
        capture.decode_frame(canonical(frame), nonce=NONCE, seq=1)
    assert error.value.reason == "ipc_binding_invalid"


@pytest.mark.parametrize("mutation", ["duplicate", "whitespace", "invalid_utf8", "nan", "infinity",
                                       "surrogate", "depth", "members", "frame_cap"])
def test_codec_strict_decoding_and_parser_caps(mutation):
    raw = capture.encode_frame("HELLO", NONCE, 0, payload("HELLO"))
    specimens = {
        "duplicate": raw.replace(b'"seq":0', b'"seq":0,"seq":0'),
        "whitespace": raw + b"\n",
        "invalid_utf8": raw.replace(b'"HELLO"', b'"\xff"'),
        "nan": raw.replace(b'"seq":0', b'"seq":NaN'),
        "infinity": raw.replace(b'"seq":0', b'"seq":Infinity'),
        "surrogate": raw.replace(b'"HELLO"', b'"\\ud800"'),
        "depth": b'{"a":{"b":{"c":{"d":{"e":0}}}}}',
        "members": canonical({str(index): 0 for index in range(65)}),
        "frame_cap": b" " * (capture.FRAME_MAX + 1),
    }
    with pytest.raises(capture.CaptureRefused) as error:
        capture.decode_frame(specimens[mutation], nonce=NONCE, seq=0)
    expected = "limit_exceeded" if mutation in {"depth", "members", "frame_cap"} else "ipc_binding_invalid"
    assert error.value.reason == expected


@pytest.mark.parametrize("detail", ["\0", "é" * 129])
def test_error_detail_is_utf8_byte_bounded_and_nul_free(detail):
    with pytest.raises(capture.CaptureRefused, match="detail string cap"):
        capture.encode_frame("ERROR", NONCE, 0, {"reason": "capture_integrity_failed", "detail": detail})
    accepted = capture.encode_frame("ERROR", NONCE, 0, {"reason": "capture_integrity_failed", "detail": "é" * 128})
    assert capture.decode_frame(accepted, nonce=NONCE, seq=0)["payload"]["detail"] == "é" * 128


class DatagramModel:
    """A recvmsg/send fault model, never evidence of kernel credentials."""
    def __init__(self):
        self.packets = []
        self.sent = []
        self.closed = False
        self.send_fault = None
        self.received = 0

    def recvmsg(self, size, ancillary_size, flags):
        assert size == capture.FRAME_MAX + 1
        assert ancillary_size == socket.CMSG_SPACE(256 * 4)
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
    return (socket.SOL_SOCKET, socket.SCM_CREDENTIALS, struct.pack("3i", *peer))


@pytest.mark.parametrize("fault", [None, "missing", "wrong_pid", "wrong_uid", "wrong_gid", "duplicate",
                                   "malformed", "rights", "truncated_rights", "truncated_data", "unknown"])
def test_receive_frame_credentials_ancillary_and_rights_closure(monkeypatch, fault):
    peer = (41, 42, 43)
    raw = capture.encode_frame("HELLO", NONCE, 0, payload("HELLO"))
    ancillary, flags = [credentials(peer)], 0
    if fault == "missing":
        ancillary = []
    elif fault in {"wrong_pid", "wrong_uid", "wrong_gid"}:
        changed = list(peer)
        changed[{"wrong_pid": 0, "wrong_uid": 1, "wrong_gid": 2}[fault]] += 1
        ancillary = [credentials(changed)]
    elif fault == "duplicate":
        ancillary *= 2
    elif fault == "malformed":
        ancillary = [(socket.SOL_SOCKET, socket.SCM_CREDENTIALS, b"bad")]
    elif fault in {"rights", "truncated_rights"}:
        ancillary += [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [801, 802]).tobytes())]
        flags = socket.MSG_CTRUNC if fault == "truncated_rights" else 0
    elif fault == "truncated_data":
        flags = socket.MSG_TRUNC
    elif fault == "unknown":
        ancillary += [(socket.SOL_SOCKET, 9999, b"unknown")]
    channel = DatagramModel()
    channel.packets.append((raw, ancillary, flags, None))
    closed = []
    monkeypatch.setattr(capture.os, "close", closed.append)
    if fault is None:
        decoded, count = capture.receive_frame(channel, peer=peer, nonce=NONCE, seq=0)
        assert decoded["kind"] == "HELLO" and count == len(raw)
    else:
        with pytest.raises(capture.CaptureRefused):
            capture.receive_frame(channel, peer=peer, nonce=NONCE, seq=0)
    assert closed == ([801, 802] if fault in {"rights", "truncated_rights"} else [])
    assert 803 not in closed  # A caller-owned foreign descriptor was never delivered.


def test_receive_eof_is_not_an_authenticated_completion():
    channel = DatagramModel()
    channel.packets.append((b"", [], 0, None))
    assert capture.receive_frame(channel, peer=(41, 42, 43), nonce=NONCE, seq=2) == (None, 0)


@pytest.fixture
def model(monkeypatch):
    """No child is started: integer handles below are explicitly modeled."""
    clock = SimpleNamespace(now=100 * capture.NS)
    binding = capture.HelperRuntimeBinding(capture.RUNTIME_SCHEMA, "1" * 64, "2" * 64, "3" * 64,
                                           "4" * 64, "5" * 64, digest(canonical(capture.ENVIRONMENT)))
    runtime_sha = digest(binding.canonical_bytes())
    lane = capture.CaptureLane()
    owner = capture.OwnerInputs(601, "/immutable/model", 602, 603, b"owner-profile", b"owner-inventory",
                                "c" * 64, "d" * 64, 1, 4, binding, b"helper-inventory", True, True, lane)
    identity = capture.ProcessIdentity(41, 700, 42, 43, 40, "/immutable/model/usr/bin/python3.12",
                                       ("fixed", "-I", "-S", "-B"), runtime_sha)
    process = capture.OwnedProcess(41, 604, identity)
    allocation = profile.OwnedAllocation("capture-" + ALLOCATION, 701, 702, **ROOT,
                                         parent_identity=(21, 22, 23), boot_nonce="f" * 64)
    channel = DatagramModel()
    slot = capture.PreparedCaptureSlot(owner, allocation, (21, 22, 23), "f" * 64, NONCE,
                                        runtime_sha, process, channel, 705, 706,
                                        prepared_at_ns=clock.now, rx_seq=2, held_fds=[705, 706, 707])
    lane.occupant = slot
    state = SimpleNamespace(clock=clock, owner=owner, slot=slot, process=process, channel=channel,
                            lane=lane, allocation=allocation, signals=[], closed=[], logs={705: [], 706: []},
                            exit_ready=False, exit_code=0, wait_results=None, wait_calls=[], reads=[])

    def select_ready(readers, writers, errors, timeout):
        assert timeout == 0, "poll/observe_exit must never block"
        ready = [item for item in readers if
                 (item is channel and channel.packets) or
                 (isinstance(item, int) and item in state.logs and state.logs[item]) or
                 (item == process.pidfd and state.exit_ready)]
        return ready, [], []

    def waitid(kind, fd, options):
        assert kind == os.P_PIDFD and fd == process.pidfd
        assert options & os.WNOHANG and options & os.WEXITED
        state.wait_calls.append(options)
        if state.wait_results is not None:
            return state.wait_results.pop(0)
        return SimpleNamespace(si_pid=identity.pid, si_code=os.CLD_EXITED, si_status=state.exit_code)

    def read(fd, count):
        assert fd in state.logs, "poll must only read retained diagnostic pipes"
        state.reads.append((fd, count))
        if not state.logs[fd]:
            raise BlockingIOError()
        value = state.logs[fd].pop(0)
        assert len(value) <= count
        return value

    def forbidden(*args, **kwargs):
        raise AssertionError("metadata-only API performed filesystem/spawn/wait work")

    monkeypatch.setattr(capture.time, "monotonic_ns", lambda: clock.now)
    monkeypatch.setattr(capture.select, "select", select_ready)
    monkeypatch.setattr(capture.os, "waitid", waitid)
    monkeypatch.setattr(capture.os, "read", read)
    monkeypatch.setattr(capture.os, "close", state.closed.append)
    monkeypatch.setattr(capture.signal, "pidfd_send_signal", lambda fd, sig: state.signals.append((fd, sig)))
    for name in ("open", "stat", "fstat", "scandir", "posix_spawn", "kill", "waitpid"):
        monkeypatch.setattr(capture.os, name, forbidden)
    monkeypatch.setattr(capture.time, "sleep", forbidden)
    for name in ("allocate_private_capture", "capture_into_owned", "load_profile", "_verify_tree"):
        monkeypatch.setattr(profile, name, forbidden)
    return state


def begin(model, *, admitted=None):
    admitted = model.clock.now if admitted is None else admitted
    return capture.begin_capture(model.slot, {"admitted_at_ns": admitted,
                                             "absolute_deadline_ns": admitted + 600 * capture.NS})


def queue_frame(model, kind="COMPLETE", *, value=None, nonce=NONCE, seq=2):
    value = payload(kind) if value is None else value
    raw = capture.encode_frame(kind, nonce, seq, value)
    model.channel.packets.append((raw, [credentials((41, 42, 43))], 0, None))


def queue_eofs(model):
    model.channel.packets.append((b"", [], 0, None))
    model.logs[705].append(b"")
    model.logs[706].append(b"")


def test_begin_preserves_outer_reservations_and_is_one_use_without_io(model):
    run = begin(model, admitted=model.clock.now - 7 * capture.NS)
    assert run.capture_deadline_ns == 183 * capture.NS
    assert run.absolute_deadline_ns == 693 * capture.NS
    assert model.slot.used and model.lane.occupant is run
    assert capture.decode_frame(model.channel.sent[0], nonce=NONCE, seq=1) == {
        "schema": capture.SCHEMA, "kind": "BEGIN", "nonce": NONCE, "seq": 1,
        "payload": {"capture_deadline_ns": 183 * capture.NS, "absolute_deadline_ns": 693 * capture.NS},
    }
    with pytest.raises(capture.CaptureRefused):
        begin(model)
    assert len(model.channel.sent) == 1


@pytest.mark.parametrize("fault", ["expired", "future_admission", "wrong_outer", "bool_admission", "extra_key", "binding"])
def test_refused_begin_consumes_slot_without_sending(model, fault):
    timing = {"admitted_at_ns": model.clock.now, "absolute_deadline_ns": model.clock.now + 600 * capture.NS}
    if fault == "expired":
        model.clock.now += 30 * capture.NS
    elif fault == "future_admission":
        timing = {key: value + capture.NS for key, value in timing.items()}
    elif fault == "wrong_outer":
        timing["absolute_deadline_ns"] += 1
    elif fault == "bool_admission":
        timing["admitted_at_ns"] = True
    elif fault == "extra_key":
        timing["path"] = "/foreign"
    else:
        model.slot.runtime_sha256 = "0" * 64
    run = capture.begin_capture(model.slot, timing)
    assert run.reason is not None and model.slot.used
    assert model.channel.sent == []
    assert model.signals == [(604, signal.SIGTERM)]
    with pytest.raises(capture.CaptureRefused):
        begin(model)
    assert model.allocation.root_fd == 701 and model.allocation.parent_fd == 702


@pytest.mark.parametrize("fault", [0, BlockingIOError(), OSError("unknown send outcome")])
def test_uncertain_begin_delivery_never_retries_or_reuses(model, fault):
    model.channel.send_fault = fault
    run = begin(model)
    assert run.reason == "ipc_binding_invalid"
    assert len(model.channel.sent) == 1 and model.slot.used
    with pytest.raises(capture.CaptureRefused):
        run.take_capture()
    assert model.closed == [] and model.lane.occupant is run


def test_prepared_idle_expiry_is_finite_and_cannot_be_rearmed(model):
    with pytest.raises(capture.CaptureRefused, match="has not expired"):
        capture.expire_prepared_slot(model.slot, model.clock.now)
    assert not model.slot.used
    model.clock.now += 30 * capture.NS
    run = capture.expire_prepared_slot(model.slot, model.clock.now)
    assert run.reason == "deadline_exceeded" and run.term_until_ns == 135 * capture.NS
    assert run.exit_until_ns == 140 * capture.NS
    assert model.channel.sent == []
    with pytest.raises(capture.CaptureRefused):
        capture.expire_prepared_slot(model.slot, model.clock.now)


def test_complete_is_provisional_until_matching_pidfd_reap_and_all_eofs(model):
    run = begin(model)
    queue_frame(model)
    assert run.poll(model.clock.now).to_record() == {"state": "running"}
    assert run.state == "completion_pending_exit" and run.complete
    with pytest.raises(capture.CaptureRefused):
        run.take_capture()
    queue_eofs(model)
    assert run.poll(model.clock.now).state == "running"  # EOF alone cannot confirm exit.
    model.exit_ready = True
    assert run.poll(model.clock.now).to_record() == {"state": "capture_ready"}
    assert model.wait_calls == [os.WEXITED | os.WNOHANG | os.WNOWAIT, os.WEXITED | os.WNOHANG]
    owned = run.take_capture()
    assert isinstance(owned, profile.OwnedCapture)
    assert (owned.root_fd, owned.parent_fd, owned.device, owned.inode, owned.mount_id) == (701, 702, 11, 12, 13)
    assert owned.identity.profile_sha256 == model.owner.profile_sha256
    assert model.allocation.root_fd == model.allocation.parent_fd == -1
    assert model.lane.occupant is owned and model.channel.closed
    assert model.closed == [705, 706, 707, 604]
    with pytest.raises(capture.CaptureRefused):
        run.take_capture()
    with pytest.raises(capture.CaptureRefused):
        run.take_quarantine()


@pytest.mark.parametrize("fault", ["missing_report", "nonzero_exit", "duplicate", "error", "wrong_root", "wrong_name",
                                   "wrong_totals", "other_slot_nonce", "replayed_seq", "early_eof", "late"])
def test_no_report_shape_exit_or_deadline_can_forge_capture(model, fault):
    run = begin(model)
    if fault == "error":
        queue_frame(model, "ERROR")
    elif fault not in {"missing_report", "early_eof"}:
        value = payload("COMPLETE")
        if fault == "wrong_root":
            value["root_identity"]["inode"] += 1
        elif fault == "wrong_name":
            value["allocation_id"] = "e" * 32
        elif fault == "wrong_totals":
            value["total_file_bytes"] += 1
        queue_frame(model, value=value, nonce="f" * 64 if fault == "other_slot_nonce" else NONCE,
                    seq=1 if fault == "replayed_seq" else 2)
        if fault == "duplicate":
            queue_frame(model, seq=3)
    queue_eofs(model)
    model.exit_ready = True
    model.exit_code = 70 if fault == "nonzero_exit" else 0
    if fault == "late":
        model.clock.now = run.capture_deadline_ns
    update = run.poll(model.clock.now)
    assert update.state == "quarantined" and run.reason is not None
    with pytest.raises(capture.CaptureRefused):
        run.take_capture()
    quarantine = run.take_quarantine()
    assert quarantine.allocation is model.allocation
    assert quarantine.process is model.process and quarantine.slot is model.slot
    assert model.lane.occupant is quarantine and model.closed == []
    with pytest.raises(capture.CaptureRefused):
        run.take_quarantine()


@pytest.mark.parametrize("fault", ["peek_wrong_pid", "reap_wrong_pid", "reap_changed_status", "no_reap", "error"])
def test_confirmed_exit_requires_readiness_and_matching_peek_reap(model, fault):
    good = SimpleNamespace(si_pid=41, si_code=os.CLD_EXITED, si_status=0)
    wrong = SimpleNamespace(si_pid=99, si_code=os.CLD_EXITED, si_status=0)
    model.process.observe_exit()
    assert not model.process.confirmed_exit and not model.wait_calls
    model.exit_ready = True
    if fault == "error":
        def unavailable(*args):
            raise ChildProcessError()
        # Assigning the model seam cannot turn it into a real wait/identity proof.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(capture.os, "waitid", unavailable)
            model.process.observe_exit()
    else:
        second = {"reap_wrong_pid": wrong, "reap_changed_status": SimpleNamespace(si_pid=41, si_code=os.CLD_EXITED, si_status=1),
                  "no_reap": None}.get(fault, good)
        model.wait_results = [wrong if fault == "peek_wrong_pid" else good, second]
        model.process.observe_exit()
    assert model.process.identity_lost and not model.process.confirmed_exit
    assert model.process.send_signal(signal.SIGKILL) is False
    assert model.signals == []


def test_lost_identity_with_no_ready_descriptors_cancels(model):
    run = begin(model)
    model.process.identity_lost = True
    assert run.poll(model.clock.now).state == "terminating"
    assert run.reason == "owned_process_identity_unavailable"
    assert model.signals == []  # No pidfd signal without retained identity; no numeric fallback.


def test_cancel_invalidates_provisional_report_and_escalates_once(model):
    run = begin(model)
    queue_frame(model)
    run.poll(model.clock.now)
    run.request_cancel(model.clock.now)
    run.request_cancel(model.clock.now + 1)
    assert not run.complete and run.reason == "cancelled"
    assert model.signals == [(604, signal.SIGTERM)]
    model.clock.now += 5 * capture.NS
    assert run.poll(model.clock.now).state == "killing"
    assert model.signals == [(604, signal.SIGTERM), (604, signal.SIGKILL)]
    model.clock.now += 5 * capture.NS
    assert run.poll(model.clock.now).to_record() == {
        "state": "quarantined_pending_io", "reason": "cancelled", "kill_action": "kill-failed"}
    run.poll(model.clock.now)
    assert len(model.signals) == 2 and model.closed == []
    quarantine = run.take_quarantine()
    assert capture.request_cleanup(quarantine).state == "blocked_pending_exit"
    assert model.lane.occupant is quarantine
    with pytest.raises(capture.CaptureRefused, match="capture lane already owned"):
        capture.prepare_capture_slot(model.owner, model.clock.now + capture.NS)
    model.exit_ready = True
    quarantine.observe_exit()
    assert quarantine.process.confirmed_exit
    assert capture.request_cleanup(quarantine).state == "queued_owned_removal"
    assert capture.request_cleanup(quarantine).state == "queued_owned_removal"
    assert model.lane.occupant is quarantine and model.closed == []
    with pytest.raises(capture.CaptureRefused):
        run.take_capture()


def test_deadline_truncates_both_cancel_graces(model):
    run = begin(model)
    model.clock.now = run.capture_deadline_ns - capture.NS
    run.request_cancel(model.clock.now)
    assert run.term_until_ns == run.exit_until_ns == run.capture_deadline_ns
    model.clock.now += capture.NS
    assert run.poll(model.clock.now).state == "quarantined_pending_io"
    assert model.signals == [(604, signal.SIGTERM), (604, signal.SIGKILL)]


@pytest.mark.parametrize("missing", ["identity", "pidfd", "lost"])
def test_no_numeric_pid_fallback_when_owned_signal_is_unavailable(model, missing):
    if missing == "identity":
        model.process.identity = None
    elif missing == "pidfd":
        model.process.pidfd = -1
    else:
        model.process.identity_lost = True
    assert model.process.send_signal(signal.SIGTERM) is False
    assert model.signals == []


@pytest.mark.parametrize("fault", ["uncertain", "closed_root", "closed_parent", "missing_mount"])
def test_cleanup_requires_live_exact_allocation_and_never_removes(model, fault):
    allocation = model.allocation
    if fault == "uncertain":
        allocation = profile.AllocationUncertain(allocation.allocation_name, 702, (21, 22, 23), "mkdir_unknown")
    else:
        setattr(allocation, {"closed_root": "root_fd", "closed_parent": "parent_fd", "missing_mount": "mount_id"}[fault], -1)
    model.process.confirmed_exit = True
    quarantine = capture.CaptureQuarantine(model.lane, allocation, model.process, model.slot, "capture_integrity_failed")
    model.lane.occupant = quarantine
    assert capture.request_cleanup(quarantine).state == "cleanup_incomplete"
    assert model.lane.occupant is quarantine and model.closed == []
    # Serialized facts cannot reconstruct a live ownership handle.
    with pytest.raises((AttributeError, TypeError)):
        capture.request_cleanup({"allocation": {"root_fd": 701}, "confirmed_exit": True})


def test_close_only_releases_handles_without_removal_or_lane_release(model):
    model.allocation.close()
    assert model.closed == [701, 702]
    assert model.allocation.root_fd == model.allocation.parent_fd == -1
    assert model.lane.occupant is model.slot


@pytest.mark.parametrize("stream", [705, 706])
def test_poll_diagnostic_limit_counts_discarded_bytes(model, stream):
    run = begin(model)
    model.slot.log_bytes[stream - 705] = 1024 * 1024
    model.logs[stream].append(b"x")
    assert run.poll(model.clock.now).state == "terminating"
    assert run.reason == "limit_exceeded" and model.signals == [(604, signal.SIGTERM)]


def test_poll_event_and_byte_budgets_do_not_drain_a_busy_peer(model):
    run = begin(model)
    for _ in range(100):
        model.channel.packets.append((b"x" * (capture.FRAME_MAX + 1), [], socket.MSG_TRUNC, None))
        model.logs[705].append(b"x" * 4096)
        model.logs[706].append(b"x" * 4096)
    run.poll(model.clock.now)
    events = model.channel.received + len(model.reads)
    bytes_scheduled = model.channel.received * (capture.FRAME_MAX + 1) + sum(count for _, count in model.reads)
    assert 0 < events <= 16 and bytes_scheduled <= 65536
    assert model.channel.packets and model.logs[705] and model.logs[706]
    assert run.reason == "ipc_binding_invalid"


def test_poll_cooperative_time_budget_stops_before_draining(model, monkeypatch):
    run = begin(model)
    model.logs[705].extend([b"x"] * 100)
    ticks = iter([model.clock.now, model.clock.now, model.clock.now, model.clock.now + 5_000_000,
                  model.clock.now + 5_000_000])
    monkeypatch.setattr(capture.time, "monotonic_ns", lambda: next(ticks, model.clock.now + 5_000_000))
    assert run.poll(model.clock.now).state == "running"
    assert len(model.reads) <= 1 and len(model.logs[705]) >= 99


def test_aggregate_control_limit_is_per_direction(model):
    run = begin(model)
    queue_frame(model)
    model.slot.rx_bytes = capture.TRAFFIC_MAX
    assert run.poll(model.clock.now).state == "terminating"
    assert run.reason == "limit_exceeded"


def test_preparation_refuses_untrusted_domain_before_any_effect(model):
    model.lane.occupant = None
    owner = replace(model.owner, dedicated_supervisor_domain=False)
    failure = capture.prepare_capture_slot(owner, model.clock.now + 20 * capture.NS)
    assert isinstance(failure, capture.CapturePreparationFailure)
    assert failure.reason == "supervisor_domain_unavailable"
    assert failure.quarantine.allocation is failure.quarantine.process is None
    assert model.lane.occupant is failure.quarantine
    assert model.channel.sent == model.closed == model.signals == []


def test_entry_source_places_real_copy_and_document_reads_after_begin():
    """A source ordering guard only; never claims bootstrap/FD enforcement."""
    source = Path(capture.__file__).with_name("native_capture_entry.py").read_text()
    tree = ast.parse(source)
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    begins = [node for node in ast.walk(main) if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "begin" for target in node.targets)]
    assert len(begins) == 1
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]
    copies = [node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "capture_into_owned"]
    loads = [node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "load_profile"]
    reads = [node for node in calls if isinstance(node.func, ast.Name) and node.func.id == "read_document"]
    assert len(copies) == len(loads) == 1 and len(reads) == 2
    assert all(node.lineno > begins[0].lineno for node in copies + loads + reads)
    assert not any(isinstance(node.func, ast.Attribute) and node.func.attr == "capture_private" for node in calls)


@pytest.fixture
def benign_split_fixture(tmp_path):
    """Real primitive fixture, authored but unrun; contains no runnable runtime."""
    donor = tmp_path / "donor"
    parent = tmp_path / "private"
    foreign = tmp_path / "foreign"
    for directory in (donor, parent, foreign):
        directory.mkdir(mode=0o700)
    (foreign / "sentinel").write_bytes(b"not a capture allocation")
    files = {
        "usr/bin/python3.12": (b"inert synthetic interpreter label", "executable"),
        "app/native_closure_entry.py": (b"# inert synthetic entry\n", "data"),
        "app/src/example.py": (b"# inert source fixture\n", "data"),
        "tools/objdiff": (b"inert synthetic checker label", "executable"),
        "dev/null": (b"", "data"),
    }
    directories = {"usr/lib/python3.12/lib-dynload", "app/vendor", "work", "dev"}
    for path in [*files, *directories]:
        components = path.split("/")
        directories.update("/".join(components[:index]) for index in range(1, len(components)))
    rows = [{"path": path, "type": "directory", "permission_class": "directory"} for path in directories]
    rows.extend({"path": path, "type": "file", "permission_class": permission,
                 "size": len(data), "sha256": digest(data)} for path, (data, permission) in files.items())
    rows.append({"path": "usr/bin/python-alias", "type": "symlink", "permission_class": "symlink", "target": "python3.12"})
    rows.sort(key=lambda row: row["path"].encode())
    for row in rows:
        target = donor / row["path"]
        if row["type"] == "directory":
            target.mkdir(mode=0o755)
        elif row["type"] == "file":
            target.write_bytes(files[row["path"]][0])
            target.chmod(0o555 if row["permission_class"] == "executable" else 0o644)
        else:
            target.symlink_to(row["target"])
    by_path = {row["path"]: row for row in rows}
    inventory_bytes = canonical({"schema": profile.INVENTORY_SCHEMA, "entries": rows})
    source_rows = [row for row in rows if row["path"].startswith(("app/src/", "app/vendor/"))]
    document = {
        "schema": profile.PROFILE_SCHEMA, "profile_id": profile.PROFILE_ID,
        "root_inventory_sha256": digest(inventory_bytes),
        "implementation_source_sha256": digest(canonical({"schema": profile.SOURCE_SCHEMA, "entries": source_rows})),
        "interpreter": {"path": "/usr/bin/python3.12", "family": "cpython-3.12", "sha256": by_path["usr/bin/python3.12"]["sha256"]},
        "entrypoint": {"path": "/app/native_closure_entry.py", "sha256": by_path["app/native_closure_entry.py"]["sha256"]},
        "checker": {"id": "synthetic-owner-selected-checker", "path": "/tools/objdiff", "sha256": by_path["tools/objdiff"]["sha256"]},
        "launcher": {"family": "bubblewrap", "source_version": "0.11.0", "sha256": "a" * 64},
        "policy": {"id": profile.POLICY_ID, "filter_sha256": "b" * 64},
        "environment": dict(profile.ENVIRONMENT), "environment_sha256": digest(canonical(dict(profile.ENVIRONMENT))),
        "supervisor_domain": "dedicated-trusted-uid",
        "work_filesystem": {"flags": ["noexec", "nosuid", "nodev"], "max_bytes": profile.MAX_TOTAL_BYTES},
    }
    profile_bytes = canonical(document)
    selected = profile.load_profile(profile_bytes, inventory_bytes, expected_profile_sha256=digest(profile_bytes),
                                    expected_inventory_sha256=digest(inventory_bytes))
    donor_fd = os.open(donor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    foreign_fd = os.open(foreign, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    handles = []
    fixture = SimpleNamespace(donor=donor, parent=parent, foreign=foreign, donor_fd=donor_fd,
                              parent_fd=parent_fd, foreign_fd=foreign_fd, selected=selected, rows=rows, files=files)

    def allocate():
        try:
            allocation = profile.allocate_private_capture(private_parent_fd=parent_fd, absolute_deadline=time.monotonic() + 90)
        except profile.CaptureFailed as error:
            if error.partial is not None:
                handles.append(error.partial)
            raise
        handles.append(allocation)
        view = profile.CaptureRootView(allocation.root_fd, allocation.device, allocation.inode, allocation.mount_id)
        return allocation, view

    fixture.allocate = allocate
    try:
        yield fixture
    finally:
        for handle in handles:
            handle.close()
        for fd in (donor_fd, parent_fd, foreign_fd):
            os.close(fd)
        # Restore permissions solely for pytest's own bounded synthetic fixture
        # teardown. This is not production removal and returns no cleanup receipt.
        for child in parent.iterdir():
            if child.is_dir() and not child.is_symlink():
                child.chmod(0o700)
                for nested in child.rglob("*"):
                    if nested.is_dir() and not nested.is_symlink():
                        nested.chmod(0o700)


def test_real_split_copy_freezes_exact_bytes_without_allocating_another_root(benign_split_fixture):
    fixture = benign_split_fixture
    allocation, view = fixture.allocate()
    assert list(fixture.parent.iterdir()) == [fixture.parent / allocation.allocation_name]
    assert os.listdir(allocation.root_fd) == []
    result = profile.capture_into_owned(fixture.selected, donor_fd=fixture.donor_fd, allocation=view,
                                       absolute_deadline=time.monotonic() + 90)
    assert result.entry_count == len(fixture.rows)
    assert result.total_file_bytes == sum(len(data) for data, _ in fixture.files.values())
    assert result.identity.profile_sha256 == fixture.selected.sha256
    assert result.identity.inventory_sha256 == fixture.selected.inventory.sha256
    assert (result.identity.device, result.identity.inode, result.identity.mount_id) == (
        allocation.device, allocation.inode, allocation.mount_id)
    root = fixture.parent / allocation.allocation_name
    assert stat.S_IMODE(os.fstat(allocation.root_fd).st_mode) == 0o555
    assert {str(path.relative_to(root)) for path in root.rglob("*")} == {row["path"] for row in fixture.rows}
    for row in fixture.rows:
        copied = root / row["path"]
        if row["type"] == "file":
            assert copied.read_bytes() == fixture.files[row["path"]][0]
            assert stat.S_IMODE(copied.stat().st_mode) == (0o555 if row["permission_class"] == "executable" else 0o444)
            assert (copied.stat().st_dev, copied.stat().st_ino) != (
                (fixture.donor / row["path"]).stat().st_dev, (fixture.donor / row["path"]).stat().st_ino)
        elif row["type"] == "directory":
            assert stat.S_IMODE(copied.stat().st_mode) == 0o555
        else:
            assert os.readlink(copied) == row["target"]
    assert list(fixture.parent.iterdir()) == [root]
    assert (fixture.foreign / "sentinel").read_bytes() == b"not a capture allocation"
    assert os.fstat(fixture.foreign_fd).st_ino == fixture.foreign.stat().st_ino
    assert os.fstat(fixture.donor_fd).st_ino == fixture.donor.stat().st_ino
    with pytest.raises(profile.ProfileRefused, match="already consumed"):
        profile.capture_into_owned(fixture.selected, donor_fd=fixture.donor_fd, allocation=view,
                                   absolute_deadline=time.monotonic() + 90)
    assert allocation.root_fd >= 0 and allocation.parent_fd >= 0


@pytest.mark.parametrize("fault", ["wrong_inode", "wrong_mount", "nonempty", "extra_donor", "missing_donor", "torn_donor"])
def test_real_split_refusal_retains_allocation_and_foreign_controls(benign_split_fixture, fault):
    fixture = benign_split_fixture
    allocation, view = fixture.allocate()
    root = fixture.parent / allocation.allocation_name
    if fault == "wrong_inode":
        view.inode += 1
    elif fault == "wrong_mount":
        view.mount_id += 1
    elif fault == "nonempty":
        (root / "already-here").write_bytes(b"not reusable")
    elif fault == "extra_donor":
        (fixture.donor / "unlisted").write_bytes(b"extra")
    elif fault == "missing_donor":
        (fixture.donor / "app/src/example.py").unlink()
    else:
        (fixture.donor / "app/src/example.py").write_bytes(b"# changed after pinning\n")
    with pytest.raises(profile.ProfileRefused):
        profile.capture_into_owned(fixture.selected, donor_fd=fixture.donor_fd, allocation=view,
                                   absolute_deadline=time.monotonic() + 90)
    assert view.used and os.fstat(allocation.root_fd).st_ino == allocation.inode
    assert os.fstat(allocation.parent_fd).st_ino == fixture.parent.stat().st_ino
    assert root.is_dir() and (fixture.foreign / "sentinel").read_bytes() == b"not a capture allocation"
    assert os.fstat(fixture.foreign_fd).st_ino == fixture.foreign.stat().st_ino
    with pytest.raises(profile.ProfileRefused, match="already consumed"):
        profile.capture_into_owned(fixture.selected, donor_fd=fixture.donor_fd, allocation=view,
                                   absolute_deadline=time.monotonic() + 90)


@pytest.mark.parametrize("fault", ["not_complete", "not_exited", "nonzero_exit", "missing_identity", "lost_identity", "missing_eof", "late"])
def test_take_capture_rechecks_retained_exit_and_deadline_before_transfer(model, fault):
    run = begin(model)
    queue_frame(model)
    queue_eofs(model)
    model.exit_ready = True
    assert run.poll(model.clock.now).state == "capture_ready"
    if fault == "not_complete":
        run.complete = False
    elif fault == "not_exited":
        model.process.confirmed_exit = False
    elif fault == "nonzero_exit":
        model.process.exit_code = 70
    elif fault == "missing_identity":
        model.process.identity = None
    elif fault == "lost_identity":
        model.process.identity_lost = True
    elif fault == "missing_eof":
        model.slot.eof[2] = False
    else:
        model.clock.now = run.capture_deadline_ns
    with pytest.raises(capture.CaptureRefused):
        run.take_capture()
    assert not run.taken and model.closed == []
    assert model.allocation.root_fd == 701 and model.allocation.parent_fd == 702


def test_confirmed_exit_without_all_diagnostic_eofs_expires_without_adoption(model):
    run = begin(model)
    queue_frame(model)
    model.channel.packets.append((b"", [], 0, None))
    model.exit_ready = True
    assert run.poll(model.clock.now).state == "running"
    assert model.process.confirmed_exit and not all(model.slot.eof)
    model.clock.now = run.capture_deadline_ns
    assert run.poll(model.clock.now).state == "quarantined"
    assert run.reason == "deadline_exceeded"
    quarantine = run.take_quarantine()
    assert quarantine.completion_received is True
    assert model.lane.occupant is quarantine and model.closed == []


def test_select_and_signal_errors_retain_finite_quarantine(model, monkeypatch):
    run = begin(model)
    def lost_select(*args):
        raise OSError("modeled descriptor loss")
    def refused_signal(*args):
        raise OSError("modeled pidfd failure")
    monkeypatch.setattr(capture.select, "select", lost_select)
    monkeypatch.setattr(capture.signal, "pidfd_send_signal", refused_signal)
    assert run.poll(model.clock.now).state == "terminating"
    assert run.reason == "owned_process_identity_unavailable"
    model.clock.now += 10 * capture.NS
    assert run.poll(model.clock.now).state == "quarantined_pending_io"
    assert not model.process.confirmed_exit and model.closed == []
    assert model.lane.occupant is run


@pytest.mark.parametrize("missing", ["parent_identity", "boot_nonce", "lane"])
def test_cleanup_rejects_missing_local_ownership_not_just_serialized_numbers(model, missing):
    model.process.confirmed_exit = True
    quarantine = capture.CaptureQuarantine(model.lane, model.allocation, model.process, model.slot, "cancelled")
    model.lane.occupant = quarantine
    if missing == "lane":
        model.lane.occupant = object()
    else:
        setattr(model.allocation, missing, None)
    assert capture.request_cleanup(quarantine).state == "cleanup_incomplete"
    assert model.closed == []


def test_runtime_binding_requires_exact_owner_schema_and_environment(model):
    raw = model.owner.helper_binding.canonical_bytes()
    assert set(json.loads(raw)) == {"schema", "runtime_inventory_sha256", "interpreter_sha256", "entry_sha256",
                                  "capture_module_sha256", "profile_module_sha256", "environment_sha256"}
    with pytest.raises(capture.CaptureRefused, match="helper binding schema"):
        replace(model.owner.helper_binding, schema="request-runtime").canonical_bytes()
    with pytest.raises(capture.CaptureRefused, match="helper environment pin"):
        replace(model.owner.helper_binding, environment_sha256="f" * 64).canonical_bytes()
    with pytest.raises(TypeError):
        capture.HelperRuntimeBinding(**dict(json.loads(raw), executable="/caller/chosen"))


def test_allocation_identity_failure_keeps_intent_and_blocks_cleanup(benign_split_fixture, monkeypatch):
    fixture = benign_split_fixture
    def identity_unavailable(*args):
        raise OSError("modeled failure after mkdir and before root identity")
    monkeypatch.setattr(profile, "_open_dir", identity_unavailable)
    with pytest.raises(profile.CaptureFailed) as error:
        fixture.allocate()
    uncertain = error.value.partial
    assert isinstance(uncertain, profile.AllocationUncertain)
    assert uncertain.disposition == "created_identity_unknown" and uncertain.root_fd == -1
    assert os.fstat(uncertain.parent_fd).st_ino == fixture.parent.stat().st_ino
    assert (fixture.parent / uncertain.allocation_name).is_dir()
    lane = capture.CaptureLane()
    quarantine = capture.CaptureQuarantine(lane, uncertain, None, None, error.value.code)
    lane.occupant = quarantine
    assert capture.request_cleanup(quarantine).state == "cleanup_incomplete"
    assert lane.occupant is quarantine
    assert (fixture.foreign / "sentinel").read_bytes() == b"not a capture allocation"


def test_begin_send_traffic_cap_refuses_without_a_datagram(model):
    model.slot.tx_bytes = capture.TRAFFIC_MAX
    run = begin(model)
    assert run.reason == "limit_exceeded" and model.slot.used
    assert model.channel.sent == [] and model.closed == []


def test_pidfd_readiness_without_wait_status_does_not_confirm_exit(model):
    model.exit_ready = True
    model.wait_results = [None]
    model.process.observe_exit()
    assert not model.process.confirmed_exit and not model.process.identity_lost
    assert model.wait_calls == [os.WEXITED | os.WNOHANG | os.WNOWAIT]
