"""Deterministic child-lifetime regressions; no real child processes are needed."""
from __future__ import annotations

import io
import queue
import signal
import threading
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.corpus.dashboard.actions import jobs

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("trigger", ["cancel", "deadline"])
def test_early_stdout_eof_keeps_cancellation_and_deadline_active(monkeypatch, trigger):
    cancel = threading.Event()
    clock = SimpleNamespace(now=0.0)
    proc = SimpleNamespace(pid=12345, stdout=io.StringIO(""), returncode=None)
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
    monkeypatch.setattr(jobs, "os", SimpleNamespace(name="posix", killpg=killpg))
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


@pytest.mark.parametrize("interrupt_monitor", [False, True])
def test_unresolved_child_retains_admission_until_exact_handle_exit(monkeypatch, interrupt_monitor):
    # Construct only the in-memory runner state: no receipt writer thread or disk.
    store = jobs.JobStore.__new__(jobs.JobStore)
    store._lock = threading.Lock()
    store._running = 0
    store._identity_held = {}
    store._pair_held = {}
    store._ghidra_held = {}
    store.executor = None
    job = jobs.JobRecord(id="owner", action_id="synthetic.writer", title="Writer", argv=["fake-child"])
    store._jobs = {job.id: job}
    store._persist_locked = lambda *args, **kwargs: None
    action = SimpleNamespace(identity_scope="database", ghidra_exclusive=True, backend="cli", mutating=True)
    monkeypatch.setattr(jobs, "action_by_id", lambda _: action)
    monkeypatch.setattr(jobs, "identity_lock_key", lambda _: "same-db")
    monkeypatch.setattr(jobs, "ghidra_lock_key", lambda _: "same-project")
    monkeypatch.setattr(jobs, "live_root", lambda: Path("."))
    polls = []
    sleeps = []
    proc = SimpleNamespace(pid=12345)

    def assert_held():
        assert store._running == 1
        assert store._identity_held == {"same-db": job.id}
        assert store._ghidra_held == {"same-project": job.id}
        assert job.ownership_unresolved
        assert job.worker_pid == proc.pid
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
        if interrupt_monitor:
            raise RuntimeError("monitor interrupted without observed child exit")

    def unresolved_executor(*args, on_unresolved, **kwargs):
        on_unresolved(proc, "termination attempts exhausted")
        return 124, "process termination observed"

    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda: 100.0, sleep=sleep))
    monkeypatch.setattr(jobs, "_default_executor", unresolved_executor)
    store._run(job.id, threading.Event())

    assert polls and all(handle is proc for handle in polls)
    if interrupt_monitor:
        assert_held()
        assert len(polls) == 1
    else:
        assert len(polls) == 3
        assert len(sleeps) == 2
        assert not job.ownership_unresolved
        assert job.finished_at == 100.0
        assert job.status == "failed"
        assert store._running == 0
        assert store._identity_held == {}
        assert store._ghidra_held == {}
