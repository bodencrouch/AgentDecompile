"""Blocking per-program auto-analysis coordination for MCP tools."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from ghidrecomp.utility import analyze_program as run_analysis

if TYPE_CHECKING:
    from ghidra.program.model.listing import Program as GhidraProgram  # pyright: ignore[reportMissingModuleSource]

    from agentdecompile_cli.context import ProgramInfo

logger = logging.getLogger(__name__)

__all__ = [
    "ProgramAnalysisTimeout",
    "analysis_gate_exempt_tool",
    "blocking_ensure_analyzed",
    "mark_program_analysis_complete",
    "program_needs_analysis",
    "wait_for_program_analysis_idle",
    "wait_for_program_analysis_ready",
]


class ProgramAnalysisTimeout(TimeoutError):
    """Ghidra auto-analysis did not become idle within the allowed wait."""


_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
# Cap entries on long-lived MCP servers; idle locks are dropped after each ensure/wait.
_MAX_PROGRAM_LOCKS = 512
# Idle polling: quick checks when analysis finishes early; backoff while Ghidra is busy.
_POLL_INTERVAL_MIN_SEC = 0.05
_POLL_INTERVAL_MAX_SEC = 1.0
_POLL_BACKOFF_FACTOR = 1.5

# Tools that manage analysis themselves or do not need an analyzed program yet.
_ANALYSIS_GATE_EXEMPT_TOOLS: frozenset[str] = frozenset(
    {
        "open",
        "importbinary",
        "analyzeprogram",
        "listprojectfiles",
        "listtools",
        "connectsharedproject",
        "syncproject",
        "svradmin",
        "debuginfo",
        "getcurrentprogram",
        # Memory inspection reads existing bytes/listing entries; analysis is explicit.
        "inspectmemory",
        "readbytes",
        # Function inventory reads only the currently defined listing.
        "listfunctions",
        # Symbol name discovery reads the existing symbol table; analysis is explicit.
        "searchsymbols",
        # A bounded function decompile must not start unbounded full-image analysis.
        # Resolve existing functions and let Ghidra report missing listing data.
        "decompilefunction",
        "decompile",
        # Version-control lifecycle tools do not require an analyzed listing yet.
        "checkoutprogram",
        "checkinprogram",
        "checkoutstatus",
        # Recovery orchestration tools do not require an analyzed Ghidra listing.
        "reconstruct",
        "status",
        "claimreport",
        "manageworkflow",
        "readworkspaceactivity",
        # Tier 0–1 external subprocess tools — no analyzed Ghidra program required.
        "runfiletriage",
        "runexternalrescan",
        "runbatchdecompile",
        "runbatchexportgzf",
        "runbatchbsimsignatures",
        "runbatchsastscan",
        "rundecompmatch",
    },
)


def analysis_gate_exempt_tool(norm_tool_name: str) -> bool:
    """Return True when call_tool should not wait on program analysis."""
    return norm_tool_name in _ANALYSIS_GATE_EXEMPT_TOOLS


def _program_supports_analysis_observation(program: GhidraProgram) -> bool:
    """Return False for test doubles and other objects that are not Ghidra programs."""
    # ProgramDB does not expose getAnalysisState in supported Ghidra releases.
    # Its persisted analysis flag is read through GhidraProgramUtilities.
    return callable(getattr(program, "getAnalysisState", None)) or all(
        callable(getattr(program, method, None))
        for method in ("getDomainFile", "getOptions", "getLanguageID")
    )


def _program_lock_key(program: GhidraProgram, program_path: str | None = None) -> str:
    try:
        df = program.getDomainFile()
        if df is not None:
            pathname = str(df.getPathname()).strip().replace("\\", "/")
            # A read-only server snapshot is backed by a transient /Untitled
            # database.  It must not merge its analysis gate with unrelated
            # snapshots; the canonical request/session path is authoritative.
            if pathname and pathname.strip('/').casefold() != "untitled":
                return pathname.lower()
    except Exception:
        # Best-effort lookup: some Program implementations may not expose a domain file.
        # Fall back to program_path/hashCode/id below to keep lock-key generation robust.
        logger.debug("Unable to derive lock key from program domain file; using fallback key", exc_info=True)
    if program_path:
        return program_path.strip().replace("\\", "/").lower()
    try:
        return f"program:{int(program.hashCode())}"
    except Exception:
        return f"program:{id(program)}"


def _lock_for_key(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


@contextmanager
def _program_analysis_lock(
    program: GhidraProgram,
    program_path: str | None = None,
) -> Iterator[str]:
    """Acquire per-program lock; always prune idle entry on exit (including errors)."""
    key = _program_lock_key(program, program_path)
    lock = _lock_for_key(key)
    try:
        with lock:
            yield key
    finally:
        _release_program_lock(key, lock)


def _release_program_lock(key: str, lock: threading.Lock) -> None:
    """Remove an idle per-program lock so the map does not grow without bound."""
    if lock.locked():
        return
    with _LOCKS_GUARD:
        if _LOCKS.get(key) is not lock or lock.locked():
            return
        _LOCKS.pop(key, None)
        if len(_LOCKS) <= _MAX_PROGRAM_LOCKS:
            return
        for other_key, other_lock in list(_LOCKS.items()):
            if len(_LOCKS) <= _MAX_PROGRAM_LOCKS:
                break
            if not other_lock.locked():
                _LOCKS.pop(other_key, None)


def _analysis_state_done(program: GhidraProgram) -> bool | None:
    try:
        st = program.getAnalysisState()
        if st is not None and hasattr(st, "isDone"):
            return bool(st.isDone())
    except Exception:
        logger.debug("Unable to read analysis state; treating as unknown", exc_info=True)
    return None


def _ghidra_utilities_pending(program: GhidraProgram) -> bool | None:
    """True when Ghidra utilities say analysis is pending; False when analyzed; None if unknown."""
    try:
        from ghidra.program.util import GhidraProgramUtilities  # pyright: ignore[reportMissingModuleSource]

        if GhidraProgramUtilities.shouldAskToAnalyze(program):
            return True
        return not bool(GhidraProgramUtilities.isAnalyzed(program))
    except Exception:
        return None


def _recorded_shared_snapshot_ready(program: GhidraProgram, program_info: ProgramInfo | None) -> bool:
    """Return whether a canonical immutable shared snapshot may pass the analysis gate.

    A server snapshot has no writable project-tree DomainFile.  Its transient
    ``/Untitled`` database name and an unavailable function-count query do not
    mean that the server program has not already been analyzed; routing either
    condition into AutoAnalysis would ask an immutable DB to mutate.  The
    checkout route records this capability separately from inventory size.
    """
    if program_info is None or not bool(getattr(program_info, "ghidra_analysis_complete", False)):
        return False
    metadata = getattr(program_info, "metadata", None)
    snapshot = metadata.get("sharedSnapshot") if isinstance(metadata, dict) else None
    if not isinstance(snapshot, dict) or snapshot.get("mode") != "read-only":
        return False
    return bool(str(snapshot.get("repositoryPath") or "").strip())


def program_needs_analysis(
    program: GhidraProgram,
    *,
    force: bool = False,
    program_info: ProgramInfo | None = None,
) -> bool:
    """True when Ghidra indicates analysis should run (incremental or full)."""
    if program is None:
        return False
    if not _program_supports_analysis_observation(program):
        return False
    if force:
        return True
    # Immutable Ghidra Server snapshots cannot accept AutoAnalysis writes.  Only
    # snapshots explicitly marked read-only with a persisted function inventory
    # bypass the gate; ordinary read-only imports retain normal analysis routing.
    if _recorded_shared_snapshot_ready(program, program_info):
        return False
    pending = _ghidra_utilities_pending(program)
    # ``getAnalysisState().isDone()`` can remain false after a completed
    # headless save, particularly for imported Mach-O and PE programs.  The
    # persisted Ghidra analyzed flag is the durable observation in that case;
    # treating the transient state as stronger makes a completed run roll its
    # own transaction back and prevents the corpus coordinator from advancing.
    if pending is False:
        return False
    state_done = _analysis_state_done(program)
    if state_done is False:
        return True
    if state_done is True:
        return False
    return True if pending is None else pending


def _program_analysis_still_running(program: GhidraProgram) -> bool:
    try:
        from ghidra.app.plugin.core.analysis import AutoAnalysisManager

        return bool(AutoAnalysisManager.getAnalysisManager(program).isAnalyzing())
    except Exception:
        pass
    state_done = _analysis_state_done(program)
    if state_done is True:
        return False
    if state_done is False:
        return True
    # A missing analysis receipt means work is needed, not that an analyzer
    # is running. Waiting for that flag before starting analysis deadlocks.
    return False


def wait_for_program_analysis_idle(program: GhidraProgram, *, max_wait_sec: float = 600.0) -> None:
    """Poll Ghidra analysis state until idle or raise ProgramAnalysisTimeout."""
    if program is None or max_wait_sec <= 0 or not _program_supports_analysis_observation(program):
        return
    deadline = time.time() + max_wait_sec
    interval = _POLL_INTERVAL_MIN_SEC
    while time.time() < deadline:
        if not _program_analysis_still_running(program):
            return
        time.sleep(interval)
        interval = min(_POLL_INTERVAL_MAX_SEC, interval * _POLL_BACKOFF_FACTOR)
    if _program_analysis_still_running(program):
        raise ProgramAnalysisTimeout(f"Ghidra analysis did not finish within {max_wait_sec}s")


def mark_program_analysis_complete(program_info: ProgramInfo | None) -> None:
    if program_info is None:
        return
    program_info.ghidra_analysis_complete = True
    try:
        program_info.analysis_complete = True
    except AttributeError:
        # Some ProgramInfo implementations expose analysis_complete as a
        # read-only property derived from ghidra_analysis_complete.
        pass


_DEFERRED_DEFAULT_ANALYZER_MARKERS: tuple[str, ...] = (
    # This analyzer launches a parallel decompiler pass over an entire Mach-O
    # image.  It is valuable when recovering Objective-C message metadata, but
    # it is not a prerequisite for the function inventory, symbols, call graph,
    # or cross-build facts used by the normal corpus preparation path.
    "objective-c message",
)


def _defer_expensive_default_analyzers(program: GhidraProgram, analyzers: list[str] | None) -> list[str]:
    """Disable non-essential full-image passes for the default preparation run.

    An explicit analyzer request retains Ghidra's configured defaults.  The
    deferred passes remain available to targeted recovery work; this only keeps
    their cost out of the first structural-analysis receipt.
    """
    if analyzers:
        return []
    try:
        from ghidra.program.model.listing import Program as GhidraProgramClass  # pyright: ignore[reportMissingImports]

        options = program.getOptions(GhidraProgramClass.ANALYSIS_PROPERTIES)
        disabled: list[str] = []
        for name in list(options.getOptionNames()):
            option_name = str(name)
            if not any(marker in option_name.casefold() for marker in _DEFERRED_DEFAULT_ANALYZER_MARKERS):
                continue
            if str(options.getType(option_name)) == "BOOLEAN_TYPE":
                options.setBoolean(option_name, False)
                disabled.append(option_name)
        if disabled:
            logger.info("analysis_deferred_analyzers program=%s analyzers=%s", program.getName(), disabled)
        return disabled
    except Exception as exc:
        # Analyzer-option names vary between Ghidra releases.  Failing to
        # recognize one must never prevent ordinary analysis from proceeding.
        logger.debug("analysis_deferred_analyzers_unavailable program=%s error=%s", program.getName(), exc)
        return []


def _run_auto_analysis(program: GhidraProgram, *, force: bool, analyzers: list[str] | None = None) -> list[str]:
    deferred = _defer_expensive_default_analyzers(program, analyzers)
    run_analysis(program, force_analysis=force)
    wait_for_program_analysis_idle(program)
    return deferred


def blocking_ensure_analyzed(
    program: GhidraProgram,
    program_info: ProgramInfo | None = None,
    *,
    program_path: str | None = None,
    force: bool = False,
    analyzers: list[str] | None = None,
) -> dict[str, Any]:
    """Run incremental analysis under a per-program lock; skip when already complete."""
    if program is None:
        return {"skipped": True, "reason": "no-program"}

    if program_info is not None and bool(getattr(program_info, "ghidra_analysis_complete", False)):
        if not program_needs_analysis(program, force=force, program_info=program_info):
            key = _program_lock_key(program, program_path)
            mark_program_analysis_complete(program_info)
            return {"skipped": True, "reason": "already-analyzed", "programKey": key}

    result: dict[str, Any]
    with _program_analysis_lock(program, program_path) as key:
        session_marked_done = program_info is not None and bool(
            getattr(program_info, "ghidra_analysis_complete", False)
        )
        if not (session_marked_done and not program_needs_analysis(program, force=force, program_info=program_info)):
            wait_for_program_analysis_idle(program)
        if not program_needs_analysis(program, force=force, program_info=program_info):
            mark_program_analysis_complete(program_info)
            result = {"skipped": True, "reason": "already-analyzed", "programKey": key}
        else:
            logger.info("program_analysis_start key=%s force=%s", key, force)
            deferred = _run_auto_analysis(program, force=force, analyzers=analyzers)
            if program_needs_analysis(program, program_info=program_info):
                raise ProgramAnalysisTimeout(
                    f"Ghidra auto-analysis did not complete for program (key={key})"
                )
            mark_program_analysis_complete(program_info)
            logger.info("program_analysis_done key=%s", key)
            result = {"ran": True, "programKey": key, "force": force, "deferredAnalyzers": deferred}
    return result


def wait_for_program_analysis_ready(
    program: GhidraProgram,
    program_info: ProgramInfo | None = None,
    *,
    program_path: str | None = None,
    max_wait_sec: float = 600.0,
) -> None:
    """Block until analysis is complete; run incremental ensure if still needed."""
    if program is None:
        return
    if not _program_supports_analysis_observation(program):
        mark_program_analysis_complete(program_info)
        return
    if program_info is not None and bool(getattr(program_info, "ghidra_analysis_complete", False)):
        if not program_needs_analysis(program, program_info=program_info):
            return
    with _program_analysis_lock(program, program_path) as key:
        if not program_needs_analysis(program, program_info=program_info):
            mark_program_analysis_complete(program_info)
            return
        wait_for_program_analysis_idle(program, max_wait_sec=max_wait_sec)
        if program_needs_analysis(program, program_info=program_info):
            logger.info("program_analysis_wait_ensure key=%s", key)
            _run_auto_analysis(program, force=False)
            wait_for_program_analysis_idle(program, max_wait_sec=max_wait_sec)
        if program_needs_analysis(program, program_info=program_info):
            raise ProgramAnalysisTimeout(
                f"Ghidra auto-analysis did not complete for program (key={key})"
            )
        mark_program_analysis_complete(program_info)
