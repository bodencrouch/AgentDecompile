"""Unit tests for blocking program analysis coordination."""

from __future__ import annotations

import sys

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agentdecompile_cli.mcp_utils import program_analysis as pa


@pytest.mark.unit
@pytest.mark.parametrize(
    "tool_name",
    sorted(pa._ANALYSIS_GATE_EXEMPT_TOOLS),
)
def test_analysis_gate_exempt_tools(tool_name: str) -> None:
    assert pa.analysis_gate_exempt_tool(tool_name) is True


@pytest.mark.unit
@pytest.mark.parametrize("tool_name", ["getfunction", "listfunctions", "decompilefunction"])
def test_analysis_gate_non_exempt_tools(tool_name: str) -> None:
    assert pa.analysis_gate_exempt_tool(tool_name) is False


@pytest.mark.unit
def test_wait_for_program_analysis_ready_marks_complete_only_when_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/bin.exe"
    program.getDomainFile.return_value = df
    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)

    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", lambda *_a, **_k: None)
    with patch.object(pa, "program_needs_analysis", side_effect=[True, True, False]):
        run_mock = MagicMock()
        monkeypatch.setattr(pa, "_run_auto_analysis", run_mock)
        pa.wait_for_program_analysis_ready(program, info, program_path="/bin.exe")

    run_mock.assert_called_once()
    assert info.ghidra_analysis_complete is True


@pytest.mark.unit
def test_wait_for_program_analysis_ready_raises_when_still_needs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/bin.exe"
    program.getDomainFile.return_value = df
    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)

    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", lambda *_a, **_k: None)
    with (
        patch.object(pa, "program_needs_analysis", return_value=True),
        patch.object(pa, "_run_auto_analysis", MagicMock()),
        pytest.raises(pa.ProgramAnalysisTimeout, match="did not complete"),
    ):
        pa.wait_for_program_analysis_ready(program, info, program_path="/bin.exe")

    assert info.ghidra_analysis_complete is False


@pytest.mark.unit
def test_program_needs_analysis_false_for_stub_without_analysis_state() -> None:
    class _StubProgram:
        def getName(self) -> str:
            return "stub"

    assert pa.program_needs_analysis(_StubProgram()) is False  # type: ignore[arg-type]


@pytest.mark.unit
def test_wait_for_ready_marks_stub_without_analysis_state_complete() -> None:
    class _StubProgram:
        def getName(self) -> str:
            return "stub"

    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)
    pa.wait_for_program_analysis_ready(_StubProgram(), info)  # type: ignore[arg-type]
    assert info.ghidra_analysis_complete is True
    assert not pa._LOCKS


@pytest.mark.unit
def test_blocking_ensure_skips_stub_without_analysis_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubProgram:
        def getName(self) -> str:
            return "stub"

    run_mock = MagicMock()
    monkeypatch.setattr(pa, "_run_ghidra_analysis", run_mock)
    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)
    result = pa.blocking_ensure_analyzed(_StubProgram(), info)  # type: ignore[arg-type]

    run_mock.assert_not_called()
    assert result.get("skipped") is True
    assert result.get("reason") == "already-analyzed"
    assert info.ghidra_analysis_complete is True
    assert not pa._LOCKS


@pytest.mark.unit
def test_program_needs_analysis_when_state_not_done() -> None:
    program = MagicMock()
    state = MagicMock()
    state.isDone.return_value = False
    program.getAnalysisState.return_value = state
    assert pa.program_needs_analysis(program) is True


@pytest.mark.unit
def test_program_needs_analysis_skips_when_state_done() -> None:
    program = MagicMock()
    state = MagicMock()
    state.isDone.return_value = True
    program.getAnalysisState.return_value = state
    assert pa.program_needs_analysis(program) is False


@pytest.mark.unit
def test_blocking_ensure_skips_when_already_analyzed(monkeypatch: pytest.MonkeyPatch) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/bin.exe"
    program.getDomainFile.return_value = df
    state = MagicMock()
    state.isDone.return_value = True
    program.getAnalysisState.return_value = state
    run_mock = MagicMock()
    monkeypatch.setattr(pa, "_run_ghidra_analysis", run_mock)

    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)
    result = pa.blocking_ensure_analyzed(program, info, program_path="/bin.exe")

    assert result.get("skipped") is True
    run_mock.assert_not_called()
    assert info.ghidra_analysis_complete is True


@pytest.mark.unit
def test_blocking_ensure_runs_analysis_when_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/bin.exe"
    program.getDomainFile.return_value = df
    state = MagicMock()
    state.isDone.side_effect = [False, True]
    program.getAnalysisState.return_value = state

    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", lambda *_a, **_k: None)
    with patch.object(pa, "program_needs_analysis", side_effect=[True, False]):
        run_mock = MagicMock()
        monkeypatch.setattr(pa, "_run_ghidra_analysis", run_mock)
        info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)
        result = pa.blocking_ensure_analyzed(program, info, program_path="/bin.exe")

    assert result.get("ran") is True
    # The gate already decided analysis is needed; the direct helper must run.
    run_mock.assert_called_once_with(program)
    program.startTransaction.assert_called_once_with("AgentDecompile auto-analysis")
    program.endTransaction.assert_called_once_with(program.startTransaction.return_value, True)
    assert info.ghidra_analysis_complete is True


@pytest.mark.unit
def test_wait_for_program_analysis_idle_raises_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = MagicMock()
    state = MagicMock()
    state.isDone.return_value = False
    program.getAnalysisState.return_value = state

    tick = iter([0.0, 5.0, 10.0])
    monkeypatch.setattr(pa.time, "time", lambda: next(tick))
    monkeypatch.setattr(pa.time, "sleep", lambda _sec: None)

    with patch.object(pa, "_program_analysis_still_running", return_value=True):
        with pytest.raises(pa.ProgramAnalysisTimeout):
            pa.wait_for_program_analysis_idle(program, max_wait_sec=10.0)


@pytest.mark.unit
def test_blocking_ensure_raises_when_still_needs_after_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/bin.exe"
    program.getDomainFile.return_value = df

    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", lambda *_a, **_k: None)
    with (
        patch.object(pa, "program_needs_analysis", return_value=True),
        pytest.raises(pa.ProgramAnalysisTimeout, match="did not complete"),
    ):
        run_mock = MagicMock()
        monkeypatch.setattr(pa, "_run_ghidra_analysis", run_mock)
        info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)
        pa.blocking_ensure_analyzed(program, info, program_path="/bin.exe")

    run_mock.assert_called_once()
    assert info.ghidra_analysis_complete is False


@pytest.mark.unit
def test_wait_for_ready_skips_when_session_marked_and_ghidra_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/session-done.exe"
    program.getDomainFile.return_value = df
    info = SimpleNamespace(ghidra_analysis_complete=True, analysis_complete=True)

    idle_mock = MagicMock()
    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", idle_mock)
    with patch.object(pa, "program_needs_analysis", return_value=False):
        pa.wait_for_program_analysis_ready(program, info, program_path="/session-done.exe")

    idle_mock.assert_not_called()


@pytest.mark.unit
def test_wait_for_ready_skips_work_when_ghidra_already_analyzed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/already-done.exe"
    program.getDomainFile.return_value = df
    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)

    idle_mock = MagicMock()
    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", idle_mock)
    with patch.object(pa, "program_needs_analysis", return_value=False):
        pa.wait_for_program_analysis_ready(program, info, program_path="/already-done.exe")

    idle_mock.assert_not_called()
    assert info.ghidra_analysis_complete is True


@pytest.mark.unit
def test_wait_for_ready_releases_lock_on_idle_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/wait-timeout.exe"
    program.getDomainFile.return_value = df

    monkeypatch.setattr(
        pa,
        "wait_for_program_analysis_idle",
        lambda *_a, **_k: (_ for _ in ()).throw(pa.ProgramAnalysisTimeout("idle timeout")),
    )
    with (
        patch.object(pa, "program_needs_analysis", return_value=True),
        pytest.raises(pa.ProgramAnalysisTimeout),
    ):
        pa.wait_for_program_analysis_ready(program, program_path="/wait-timeout.exe")

    assert "/wait-timeout.exe" not in pa._LOCKS


@pytest.mark.unit
def test_blocking_ensure_releases_lock_on_analysis_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/release-on-error.exe"
    program.getDomainFile.return_value = df
    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)

    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", lambda *_a, **_k: None)

    def _boom(*_a, **_k):
        raise RuntimeError("analysis failed")

    monkeypatch.setattr(pa, "_run_ghidra_analysis", _boom)
    with patch.object(pa, "program_needs_analysis", return_value=True):
        with pytest.raises(RuntimeError, match="analysis failed"):
            pa.blocking_ensure_analyzed(program, info, program_path="/release-on-error.exe")

    program.startTransaction.assert_called_once_with("AgentDecompile auto-analysis")
    program.endTransaction.assert_called_once_with(program.startTransaction.return_value, True)
    assert "/release-on-error.exe" not in pa._LOCKS


@pytest.mark.unit
def test_blocking_ensure_releases_lock_after_run(monkeypatch: pytest.MonkeyPatch) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/release-after-ensure.exe"
    program.getDomainFile.return_value = df
    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)

    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", lambda *_a, **_k: None)
    with patch.object(pa, "program_needs_analysis", side_effect=[True, False]):
        monkeypatch.setattr(pa, "_run_ghidra_analysis", MagicMock())
        pa.blocking_ensure_analyzed(program, info, program_path="/release-after-ensure.exe")

    assert "/release-after-ensure.exe" not in pa._LOCKS


@pytest.mark.unit
def test_blocking_ensure_skips_idle_wait_when_session_already_analyzed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/bin.exe"
    program.getDomainFile.return_value = df
    info = SimpleNamespace(ghidra_analysis_complete=True, analysis_complete=True)

    idle_mock = MagicMock()
    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", idle_mock)
    with patch.object(pa, "program_needs_analysis", return_value=False):
        result = pa.blocking_ensure_analyzed(program, info, program_path="/bin.exe")

    idle_mock.assert_not_called()
    assert result.get("skipped") is True
    assert result.get("programKey") == "/bin.exe"
    assert "/bin.exe" not in pa._LOCKS


@pytest.mark.unit
def test_blocking_ensure_prelock_skip_when_session_marked_and_ghidra_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/prelock-skip.exe"
    program.getDomainFile.return_value = df
    info = SimpleNamespace(ghidra_analysis_complete=True, analysis_complete=True)

    idle_mock = MagicMock()
    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", idle_mock)
    with patch.object(pa, "program_needs_analysis", return_value=False):
        result = pa.blocking_ensure_analyzed(program, info, program_path="/prelock-skip.exe")

    idle_mock.assert_not_called()
    assert result == {
        "skipped": True,
        "reason": "already-analyzed",
        "programKey": "/prelock-skip.exe",
    }
    assert "/prelock-skip.exe" not in pa._LOCKS


@pytest.mark.unit
def test_wait_for_program_analysis_idle_uses_adaptive_polling() -> None:
    program = MagicMock()
    sleeps: list[float] = []
    with (
        patch.object(pa.time, "time", side_effect=[0.0, 0.0, 0.1, 10.0]),
        patch.object(pa.time, "sleep", side_effect=lambda sec: sleeps.append(sec)),
        patch.object(pa, "_program_analysis_still_running", side_effect=[True, False]),
    ):
        pa.wait_for_program_analysis_idle(program, max_wait_sec=600.0)

    assert len(sleeps) == 1
    assert sleeps[0] == pa._POLL_INTERVAL_MIN_SEC


@pytest.mark.unit
def test_release_program_lock_prunes_idle_entry() -> None:
    key = "/prune-test.exe"
    lock = pa._lock_for_key(key)
    assert key in pa._LOCKS
    pa._release_program_lock(key, lock)
    assert key not in pa._LOCKS


@pytest.mark.unit
def test_release_program_lock_keeps_locked_entry() -> None:
    key = "/locked-test.exe"
    lock = pa._lock_for_key(key)
    lock.acquire()
    try:
        pa._release_program_lock(key, lock)
        assert key in pa._LOCKS
    finally:
        lock.release()
    pa._release_program_lock(key, lock)
    assert key not in pa._LOCKS


@pytest.mark.unit
def test_program_analysis_module_exports_public_api() -> None:
    expected = {
        "ProgramAnalysisIncomplete",
        "ProgramAnalysisTimeout",
        "analysis_failure",
        "analysis_gate_exempt_tool",
        "blocking_ensure_analyzed",
        "clear_analysis_failure",
        "mark_program_analysis_complete",
        "program_needs_analysis",
        "wait_for_program_analysis_idle",
        "wait_for_program_analysis_ready",
    }
    assert set(pa.__all__) == expected
    for name in pa.__all__:
        assert hasattr(pa, name), f"missing export: {name}"


@pytest.mark.unit
def test_gate_needed_but_ghidra_not_asking_still_runs_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh import: shouldAskToAnalyze is False yet isAnalyzed is False.

    The coordinator has already established that analysis is needed, so the
    direct Ghidra helper must not apply a second shouldAskToAnalyze gate.
    """
    program = MagicMock(spec=["getDomainFile", "getOptions", "getLanguageID", "getName", "hashCode"])
    df = MagicMock()
    df.getPathname.return_value = "/fresh.bin"
    program.getDomainFile.return_value = df
    flags = {"analyzed": False}

    def fake_direct_analysis(prog):
        assert prog is program
        flags["analyzed"] = True

    monkeypatch.setattr(pa, "_run_ghidra_analysis", fake_direct_analysis)
    monkeypatch.setattr(pa, "_ghidra_utilities_pending", lambda _p: not flags["analyzed"])
    monkeypatch.setattr(pa, "wait_for_program_analysis_idle", lambda *_a, **_k: None)
    monkeypatch.setattr(pa, "_defer_expensive_default_analyzers", lambda *_a, **_k: [])

    info = SimpleNamespace(ghidra_analysis_complete=False, analysis_complete=False)
    result = pa.blocking_ensure_analyzed(program, info, program_path="/fresh.bin")

    assert result.get("ran") is True
    assert flags["analyzed"] is True
    assert info.ghidra_analysis_complete is True


@pytest.mark.unit
@pytest.mark.parametrize("flag_method", ["setAnalyzedFlag", "markProgramAnalyzed"])
def test_direct_analysis_uses_bundle_host_and_keeps_stdout_clean(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag_method: str,
) -> None:
    events: list[tuple[object, ...]] = []
    program = SimpleNamespace(getName=lambda: "fixture.bin")

    class FakeScriptUtil:
        @staticmethod
        def acquireBundleHostReference() -> None:
            events.append(("acquire",))

        @staticmethod
        def releaseBundleHostReference() -> None:
            events.append(("release",))

    class FakeFlatProgramAPI:
        def __init__(self, selected_program: object) -> None:
            events.append(("flat-api", selected_program))

        def analyzeAll(self, selected_program: object) -> None:
            events.append(("analyze", selected_program))

    class FakeProgramUtilities:
        pass

    if flag_method == "setAnalyzedFlag":
        setattr(
            FakeProgramUtilities,
            flag_method,
            staticmethod(lambda selected_program, analyzed: events.append(("flag", selected_program, analyzed))),
        )
    else:
        setattr(
            FakeProgramUtilities,
            flag_method,
            staticmethod(lambda selected_program: events.append(("flag", selected_program, True))),
        )
    monkeypatch.setitem(sys.modules, "ghidra.app.script", SimpleNamespace(GhidraScriptUtil=FakeScriptUtil))
    monkeypatch.setitem(sys.modules, "ghidra.program.flatapi", SimpleNamespace(FlatProgramAPI=FakeFlatProgramAPI))
    monkeypatch.setitem(
        sys.modules,
        "ghidra.program.util",
        SimpleNamespace(GhidraProgramUtilities=FakeProgramUtilities),
    )

    pa._run_ghidra_analysis(program)  # type: ignore[arg-type]

    assert capsys.readouterr().out == ""
    assert events == [
        ("flat-api", program),
        ("acquire",),
        ("analyze", program),
        ("flag", program, True),
        ("release",),
    ]


@pytest.mark.unit
def test_direct_analysis_releases_bundle_host_when_analyzer_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    program = SimpleNamespace(getName=lambda: "fixture.bin")

    class FakeScriptUtil:
        @staticmethod
        def acquireBundleHostReference() -> None:
            events.append("acquire")

        @staticmethod
        def releaseBundleHostReference() -> None:
            events.append("release")

    class FakeFlatProgramAPI:
        def __init__(self, _program: object) -> None:
            pass

        def analyzeAll(self, _program: object) -> None:
            events.append("analyze")
            raise RuntimeError("analyzer failed")

    monkeypatch.setitem(sys.modules, "ghidra.app.script", SimpleNamespace(GhidraScriptUtil=FakeScriptUtil))
    monkeypatch.setitem(sys.modules, "ghidra.program.flatapi", SimpleNamespace(FlatProgramAPI=FakeFlatProgramAPI))
    monkeypatch.setitem(
        sys.modules,
        "ghidra.program.util",
        SimpleNamespace(GhidraProgramUtilities=SimpleNamespace(setAnalyzedFlag=lambda *_args: None)),
    )

    with pytest.raises(RuntimeError, match="analyzer failed"):
        pa._run_ghidra_analysis(program)  # type: ignore[arg-type]

    assert events == ["acquire", "analyze", "release"]
