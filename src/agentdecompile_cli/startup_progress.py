"""Progress for slow local PyGhidra startup without changing its lifecycle."""

from __future__ import annotations

import sys
import threading
import time

from collections.abc import Iterator
from contextlib import contextmanager


def _startup_phase(thread_id: int) -> str:
    """Classify known frames without reading source, paths, or frame locals."""
    calls: set[tuple[str, str]] = set()
    frame = sys._current_frames().get(thread_id)
    try:
        while frame is not None:
            calls.add((frame.f_globals.get("__name__", ""), frame.f_code.co_name))
            frame = frame.f_back
    finally:
        del frame

    if ("importlib.metadata", "entry_points") in calls:
        return "discovering Python plugins"
    if ("pyghidra.launcher", "_pre_launch_init") in calls:
        return "initializing Ghidra plugins"
    if ("pyghidra.launcher", "_launch") in calls:
        return "initializing the Ghidra application"
    if ("pyghidra.launcher", "_plugin_lock") in calls:
        return "preparing Ghidra plugins"
    if ("jpype._core", "startJVM") in calls:
        return "starting the JVM"
    if ("pyghidra.launcher", "_setup_java") in calls:
        return "preparing the JVM"
    if ("pyghidra.launcher", "__init__") in calls:
        return "configuring the JVM"
    return "initializing PyGhidra"


@contextmanager
def report_slow_pyghidra_startup(interval: float = 10.0) -> Iterator[None]:
    """Report long waits; stop and join the reporter before returning or raising."""
    thread_id = threading.get_ident()
    started = time.monotonic()
    stopped = threading.Event()

    def report() -> None:
        while not stopped.wait(interval):
            try:
                phase = _startup_phase(thread_id)
                elapsed = time.monotonic() - started
                sys.stderr.write(
                    f"Local startup: {elapsed:.0f}s elapsed; {phase}. "
                    "The local project has not been opened yet.\n"
                )
                sys.stderr.flush()
            except Exception:
                # Optional diagnostics must not interrupt startup or emit a traceback.
                return

    monitor = threading.Thread(target=report, name="agentdecompile-startup-progress", daemon=True)
    try:
        monitor.start()
    except RuntimeError:
        # Keep startup available if the process cannot allocate a reporting thread.
        yield
        return
    try:
        yield
    finally:
        stopped.set()
        monitor.join()
