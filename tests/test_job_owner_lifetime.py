"""Deterministic child-lifetime regressions; no real child processes are needed."""
from __future__ import annotations

import queue
import signal
import threading
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.corpus.dashboard.actions import jobs
from agentdecompile_recovery.corpus import supervision

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("trigger", ["cancel", "deadline"])
def test_early_stdout_eof_keeps_cancellation_and_deadline_active(monkeypatch, trigger):
    cancel = threading.Event()
    clock = SimpleNamespace(now=0.0)
    proc = SimpleNamespace(pid=12345, stdout=SimpleNamespace(fileno=lambda: 17, close=lambda: None), returncode=None)
    proc.poll = lambda: proc.returncode
    signals = []

    def killpg(pid, sig):
        assert pid == proc.pid
        signals.append(sig)
        # Ignore TERM to exercise escalation even after the pipe closes.
        if sig == signal.SIGKILL:
            proc.returncode = -signal.SIGKILL

    def unexpected_wait(**kwargs):
        pytest.fail("EOF transferred a live child out of the cancellation loop")

    proc.wait = unexpected_wait

    class InlineThread:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

        def join(self, **kwargs):
            pass

    class OutputQueue:
        def __init__(self, **kwargs):
            self.items = deque()

        def put(self, item, **kwargs):
            self.items.append(item)

        def get(self, **kwargs):
            clock.now += 1.0
            assert clock.now < 20, "executor failed to terminate after escalation"
            if trigger == "cancel" and clock.now >= 2:
                cancel.set()
            if self.items:
                return self.items.popleft()
            raise queue.Empty

    monkeypatch.setattr(jobs, "threading", SimpleNamespace(Event=threading.Event, Thread=InlineThread))
    monkeypatch.setattr(jobs, "queue", SimpleNamespace(Queue=OutputQueue, Empty=queue.Empty, Full=queue.Full))
    monkeypatch.setattr(jobs, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(jobs, "os", SimpleNamespace(name="posix", killpg=killpg,
                                             set_blocking=lambda *_: None, read=lambda *_: b""))
    monkeypatch.setattr(supervision, "process_identity", lambda pid: {"pid": pid, "start_ticks": "1", "boot_id": "fake"})
    monkeypatch.setattr(supervision, "session_clearance", lambda _: "clear" if proc.returncode is not None else "occupied")
    monkeypatch.setattr(jobs, "isolated_job_env", lambda argv: {})
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: proc)

    code, log = jobs._default_executor(
        ["fake-child"], Path("."), cancel,
        timeout_seconds=2, unlimited=trigger == "cancel",
        on_unresolved=lambda *_: pytest.fail("responsive child should not need an ownership monitor"),
    )

    assert signal.SIGTERM in signals
    assert signals[-1] == signal.SIGKILL
    assert code == (124 if trigger == "deadline" else -signal.SIGKILL)
    assert ("[timed out after 2 seconds]" if trigger == "deadline" else "[cancelled]") in log


@pytest.mark.parametrize("outcome", ["clear", "occupied", "interrupted"])
def test_monitor_exit_releases_capacity_but_not_unresolved_resources(monkeypatch, outcome):
    # Construct only the in-memory runner state: no receipt writer thread or disk.
    store = jobs.JobStore.__new__(jobs.JobStore)
    store._lock = threading.Lock()
    store._running = 1  # Unrelated worker must remain counted.
    monkeypatch.setattr(jobs, "MAX_CONCURRENT", 3)
    store._identity_held = {}
    store._pair_held = {}
    store._ghidra_held = {}
    store._external_held = {}
    store._cross_active = set()
    store._cross_leases = {}
    store._restore_reservations_locked = lambda: None
    store.executor = None
    job = jobs.JobRecord(id="owner", action_id="synthetic.writer", title="Writer", argv=["fake-child"])
    store._jobs = {job.id: job}
    receipts = []
    store._persist_locked = lambda *args, **kwargs: receipts.append(job.to_dict())
    action = SimpleNamespace(id=job.action_id, identity_scope="database", ghidra_exclusive=True, backend="cli", mutating=True)
    monkeypatch.setattr(jobs, "action_by_id", lambda _: action)
    monkeypatch.setattr(jobs, "identity_lock_key", lambda _: "same-db")
    monkeypatch.setattr(jobs, "ghidra_lock_key", lambda _: "same-project")
    monkeypatch.setattr(jobs, "live_root", lambda: Path("."))
    polls = []
    sleeps = []
    proc = SimpleNamespace(pid=12345)

    def assert_held():
        assert store._running == 2
        assert store._identity_held == {"same-db": job.id}
        assert store._ghidra_held == {"same-project": job.id}
        assert job.to_dict()["ownershipUnresolved"]
        assert job.to_dict()["workerPid"] == proc.pid
        assert job.status == "cancelling"
        assert job.finished_at is None

    def poll():
        assert_held()
        polls.append(proc)
        if len(polls) == 1:
            raise OSError("temporary observation failure")
        return -signal.SIGKILL if len(polls) == 3 else None

    proc.poll = poll

    def sleep(_):
        assert_held()
        sleeps.append(True)
        if outcome == "interrupted":
            raise RuntimeError("monitor interrupted without observed child exit")

    owner = {"pid": proc.pid, "start_ticks": "synthetic", "boot_id": "synthetic"}
    monkeypatch.setattr(supervision, "session_clearance", lambda _: outcome)

    def unresolved_executor(*args, on_unresolved, on_started, **kwargs):
        on_started(owner)
        on_unresolved(proc, "termination attempts exhausted")
        if supervision.session_clearance(owner) != "clear":
            return 124, "[process did not reach a terminal state; ownership remains unresolved]"
        return 124, "process termination observed"

    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda: 100.0, sleep=sleep))
    monkeypatch.setattr(jobs, "_default_executor", unresolved_executor)
    store._run(job.id, threading.Event())

    assert polls and all(handle is proc for handle in polls)
    assert job.finished_at == 100.0
    assert job.status == "failed"
    assert store._running == 1
    assert job.execution_owner == owner
    assert receipts[-1]["status"] == "failed"
    assert receipts[-1]["finishedAt"] == 100.0
    if outcome == "interrupted":
        assert len(polls) == 1
        assert "resource reconciliation required" in job.log_reason
    else:
        assert len(polls) == 3
        assert len(sleeps) == 2
    if outcome == "clear":
        assert not job.to_dict()["ownershipUnresolved"]
        assert store._identity_held == {}
        assert store._ghidra_held == {}
    else:
        assert job.to_dict()["ownershipUnresolved"]
        assert store._identity_held == {"same-db": job.id}
        assert store._ghidra_held == {"same-project": job.id}
        assert receipts[-1]["resourceDisposition"] == "quarantined"
