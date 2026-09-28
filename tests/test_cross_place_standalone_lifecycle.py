"""Bounded standalone executor checks using private Python children, no compiler."""
import os
import sys
import threading
import time

import pytest

from agentdecompile_recovery.corpus import cross_place as cp
from agentdecompile_recovery.corpus.supervision import session_clearance


def test_cancel_before_spawn_does_not_create_child(monkeypatch):
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(cp.subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected spawn"))
    assert cp._standalone_execute([], (), cancel) == (1, "[cancelled before spawn]")


def test_owner_callback_failure_reaps_real_child():
    owners = []
    def fail(owner):
        owners.append(owner)
        raise OSError("owner persistence failed")
    with pytest.raises(OSError, match="owner persistence failed"):
        cp._standalone_execute([sys.executable, "-I", "-S", "-c", "import time;time.sleep(30)"],
                               (), threading.Event(), on_started=fail)
    assert len(owners) == 1
    assert session_clearance(owners[0]) == "clear"


def test_silent_open_pipe_does_not_strand_reader_after_child_exit(monkeypatch):
    # The fixture itself retains a write endpoint. This isolates pipe-reader
    # shutdown from process-survivor policy, covered by the catalog fixtures.
    read_fd, write_fd = os.pipe()
    real_popen = cp.subprocess.Popen
    children = []
    owners = []
    def spawn(*args, **kwargs):
        kwargs["stdout"] = write_fd
        child = real_popen(*args, **kwargs)
        child.stdout = os.fdopen(read_fd, "rb", buffering=0)
        children.append(child)
        return child
    monkeypatch.setattr(cp.subprocess, "Popen", spawn)
    try:
        start = time.monotonic()
        code, output = cp._standalone_execute([sys.executable, "-I", "-S", "-c", "pass"],
                                              (), threading.Event(), on_started=owners.append)
        assert code == 0 and output == ""
        assert time.monotonic() - start < 6
        assert session_clearance(owners[0]) == "clear"
        assert not any(t.name == f"agentdecompile-standalone-output-{children[0].pid}"
                       for t in threading.enumerate())
    finally:
        os.close(write_fd)
        if not children:
            os.close(read_fd)
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)
            if child.stdout is not None:
                child.stdout.close()


def test_watch_delay_observes_cancellation():
    cancel = threading.Event()
    timer = threading.Timer(.05, cancel.set)
    timer.start()
    try:
        start = time.monotonic()
        assert cp._watch_wait(30, cancel) is True
        assert time.monotonic() - start < 2
    finally:
        timer.join(timeout=1)
