"""Progress for slow local PyGhidra startup without changing its lifecycle."""

from __future__ import annotations

import sys
import threading
import time

from collections.abc import Callable, Iterator
from contextlib import contextmanager


def _active_calls(thread_id: int) -> set[tuple[str, str]]:
    """Read frame identities without source, paths, or frame locals."""
    calls: set[tuple[str, str]] = set()
    frame = sys._current_frames().get(thread_id)
    try:
        while frame is not None:
            calls.add((frame.f_globals.get("__name__", ""), frame.f_code.co_name))
            frame = frame.f_back
    finally:
        del frame

    return calls


def _startup_phase(thread_id: int) -> str:
    calls = _active_calls(thread_id)
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


def local_tool_phase(thread_id: int) -> str:
    """Identify synchronous tool work; an async suspension remains unspecified."""
    calls = _active_calls(thread_id)
    prefix = "agentdecompile_cli.mcp_server."
    for module, function, label in (
        ("providers._collectors", "_get_function_list", "collecting compatibility function inventory"),
        ("providers._collectors", "_get_external_function_list", "collecting external functions"),
        ("providers.functions", "scan", "scanning function names"),
        ("providers.functions", "_fast_search_existing_functions", "preparing or rendering function search"),
        ("providers.functions", "_filtered_function_rows", "collecting filtered function metadata"),
        ("program_metadata", "collect_program_summary", "collecting response program metadata"),
        ("tool_providers", "_activate_local_program_by_path", "activating requested local program"),
    ):
        if (prefix + module, function) in calls:
            return label
    return "executing local tool (phase unavailable)"


@contextmanager
def report_local_phase(operation: str, *, scope: str = "Local startup") -> Iterator[None]:
    """Emit elapsed time on exit, without changing failures or response payloads."""
    started = time.monotonic()
    outcome = "completed"
    try:
        yield
    except BaseException:
        outcome = "failed"
        raise
    finally:
        try:
            sys.stderr.write(f"{scope}: {operation} {outcome} in {time.monotonic() - started:.2f}s.\n")
            sys.stderr.flush()
        except Exception:
            pass


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


@contextmanager
def report_slow_local_operation(
    operation: str, interval: float = 10.0, *, scope: str = "Local startup",
    phase: Callable[[int], str] | None = None,
) -> Iterator[None]:
    """Report lifecycle progress without exposing project paths or data."""
    thread_id = threading.get_ident()
    started = time.monotonic()
    stopped = threading.Event()

    def report() -> None:
        while not stopped.wait(interval):
            try:
                elapsed = time.monotonic() - started
                label = phase(thread_id) if phase is not None else operation
                sys.stderr.write(f"{scope}: {elapsed:.0f}s elapsed; {label}.\n")
                sys.stderr.flush()
            except Exception:
                return

    monitor = threading.Thread(target=report, name="agentdecompile-local-operation-progress", daemon=True)
    try:
        monitor.start()
    except RuntimeError:
        yield
        return
    try:
        yield
    finally:
        stopped.set()
        monitor.join()
