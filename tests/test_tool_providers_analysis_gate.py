"""Unit tests for ToolProviderManager pre-dispatch analysis gate."""

from __future__ import annotations

import asyncio
import json
import threading

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import agentdecompile_cli.mcp_server.program_metadata as program_metadata_module
import agentdecompile_cli.mcp_server.providers.functions as functions_module
import pytest

from agentdecompile_cli.mcp_server.providers.functions import FunctionToolProvider
from agentdecompile_cli.mcp_server.tool_providers import (
    ActionableError,
    ToolProvider,
    ToolProviderManager,
    analysis_timeout_error_response,
    create_success_response,
    resolve_domain_program_path,
)
from agentdecompile_cli.mcp_utils.program_analysis import ProgramAnalysisTimeout
from mcp import types


class _GateProbeProvider(ToolProvider):
    """Minimal provider for list-functions, list-project-files, and open."""

    HANDLERS = {
        "listfunctions": "_handle_probe",
        "listprojectfiles": "_handle_list_project_files",
        "checkoutprogram": "_handle_checkout_program",
        "open": "_handle_open",
        "scopeerror": "_handle_scope_error",
    }

    def list_tools(self) -> list[types.Tool]:
        return [
            types.Tool(
                name="list-functions",
                description="probe",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            types.Tool(
                name="list-project-files",
                description="probe",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            types.Tool(
                name="checkout-program",
                description="probe vc exempt",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            types.Tool(
                name="open",
                description="probe exempt open",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            types.Tool(
                name="scope-error",
                description="probe recursive scope",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
        ]

    async def _handle_open(self, _args: dict):
        raise ProgramAnalysisTimeout("Ghidra auto-analysis did not complete during open")

    async def _handle_probe(self, _args: dict, *, program_info=None):
        return create_success_response(
            {
                "ok": True,
                "programPath": str(getattr(program_info, "file_path", "")),
            }
        )

    async def _handle_list_project_files(self, _args: dict, *, program_info=None):
        return create_success_response(
            {
                "programs": [],
                "programPath": str(getattr(program_info, "file_path", "")),
            }
        )

    async def _handle_checkout_program(self, _args: dict):
        return create_success_response({"checkedOut": True})

    async def _handle_scope_error(self, _args: dict, *, program_info=None):
        raise ActionableError(
            "scope probe failed",
            next_steps=["Call `list-project-files` to inspect the same program scope."],
        )


@pytest.fixture
def gate_manager() -> ToolProviderManager:
    manager = ToolProviderManager()
    manager._register(_GateProbeProvider())
    return manager


@pytest.fixture
def program_info() -> SimpleNamespace:
    program = MagicMock()
    df = MagicMock()
    df.getPathname.return_value = "/repo/other.exe"
    program.getDomainFile.return_value = df
    return SimpleNamespace(program=program, ghidra_analysis_complete=False)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("activate_lifecycle", [False, True])
@pytest.mark.parametrize("real_function_provider", [False, True])
async def test_call_scoped_program_survives_two_program_interleaving(
    gate_manager: ToolProviderManager,
    activate_lifecycle: bool,
    real_function_provider: bool,
) -> None:
    program_a = MagicMock()
    program_a.getDomainFile.return_value.getPathname.return_value = "/repo/a.exe"
    info_a = SimpleNamespace(
        program=program_a,
        file_path="/repo/a.exe",
        ghidra_analysis_complete=False,
    )
    program_b = MagicMock()
    program_b.getDomainFile.return_value.getPathname.return_value = "/repo/b.exe"
    info_b = SimpleNamespace(
        program=program_b,
        file_path="/repo/b.exe",
        ghidra_analysis_complete=False,
    )
    if real_function_provider:
        gate_manager._register(FunctionToolProvider())
    provider = gate_manager.providers[-1]
    gate_manager.set_program_info(info_a)
    lifecycle_wrapper_a = provider.ghidra_tools
    a_waiting = asyncio.Event()
    release_a = threading.Event()
    loop = asyncio.get_running_loop()
    gate_calls = []
    collected_programs = []

    def gate_wait(program, info, *, program_path):
        # Keep the real asyncio.to_thread boundary: the blocking event belongs
        # to the worker thread, and the event loop notification is thread-safe.
        gate_calls.append((program, info, program_path))
        if info is info_a:
            loop.call_soon_threadsafe(a_waiting.set)
            assert release_a.wait(timeout=5), "Timed out waiting to resume program A"

    def collect(program, **_kwargs):
        collected_programs.append(program)
        return [{
            "name": "program-A" if program is program_a else "program-B",
            "address": "1000", "size": 4, "isExternal": False,
            "isThunk": False, "parameterCount": 0,
            "signature": "void entry()", "callingConvention": "cdecl",
        }]

    def get_program_info(_session_id: str, key: str | None):
        return {"/repo/a.exe": info_a, "/repo/b.exe": info_b}.get(key)

    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_program_info",
            side_effect=get_program_info,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=None,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_project_handle",
            return_value=None,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_utils.program_analysis.wait_for_program_analysis_ready",
            side_effect=gate_wait,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.analysis_skipped_warning", return_value=None),
        patch.object(functions_module, "collect_functions", side_effect=collect),
    ):
        call_a = asyncio.create_task(
            gate_manager.call_tool(
                "list-functions",
                {"programPath": "/repo/a.exe", "responseFormat": "json"},
            )
        )
        try:
            await asyncio.wait_for(a_waiting.wait(), timeout=3)
            result_b = await asyncio.wait_for(
                gate_manager.call_tool(
                    "list-functions",
                    {"programPath": "/repo/b.exe", "responseFormat": "json"},
                ),
                timeout=3,
            )
            assert provider.program_info is info_a
            assert provider.ghidra_tools is lifecycle_wrapper_a
            if activate_lifecycle:
                # Deliberate activation is permitted while A is in flight.
                gate_manager.set_program_info(info_b)
            expected_default = info_b if activate_lifecycle else info_a
            lifecycle_wrapper = provider.ghidra_tools
        finally:
            release_a.set()
            result_a = await asyncio.wait_for(call_a, timeout=3)
        future_result = await asyncio.wait_for(
            gate_manager.call_tool("list-functions", {"responseFormat": "json"}),
            timeout=3,
        )

    payload_a = json.loads(result_a[0].text)
    payload_b = json.loads(result_b[0].text)
    future_payload = json.loads(future_result[0].text)
    if real_function_provider:
        assert payload_a["results"][0]["name"] == "program-A"
        assert payload_b["results"][0]["name"] == "program-B"
        assert future_payload["results"][0]["name"] == ("program-B" if activate_lifecycle else "program-A")
        assert collected_programs == [program_b, program_a, expected_default.program]
    else:
        assert payload_a["programPath"] == "/repo/a.exe"
        assert payload_b["programPath"] == "/repo/b.exe"
        assert future_payload["programPath"] == expected_default.file_path
    assert gate_calls == [
        (program_a, info_a, "/repo/a.exe"),
        (program_b, info_b, "/repo/b.exe"),
        (expected_default.program, expected_default, expected_default.file_path),
    ]
    assert gate_manager.program_info is expected_default
    assert provider.program_info is expected_default
    assert provider.ghidra_tools is lifecycle_wrapper


@pytest.mark.unit
@pytest.mark.asyncio
async def test_explicit_none_does_not_borrow_lifecycle_program(
    gate_manager: ToolProviderManager,
) -> None:
    lifecycle_info = SimpleNamespace(program=MagicMock(), file_path="/repo/lifecycle.exe")
    gate_manager.set_program_info(lifecycle_info)

    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=lifecycle_info,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
    ):
        result = await gate_manager.call_tool(
            "list-project-files",
            {"responseFormat": "json"},
            program_info=None,
        )

    assert json.loads(result[0].text)["programPath"] == ""
    assert gate_manager.program_info is lifecycle_info
    assert gate_manager.providers[-1].program_info is lifecycle_info


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prerequisite_recursion_preserves_call_scoped_program(
    gate_manager: ToolProviderManager,
) -> None:
    scoped_info = SimpleNamespace(
        program=MagicMock(),
        file_path="/repo/scoped.exe",
        ghidra_analysis_complete=False,
    )

    with (
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_utils.program_analysis.wait_for_program_analysis_ready",
            return_value=None,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.analysis_skipped_warning", return_value=None),
    ):
        result = await asyncio.wait_for(
            gate_manager.call_tool(
                "scope-error",
                {"responseFormat": "json"},
                program_info=scoped_info,
            ),
            timeout=3,
        )

    payload = json.loads(result[0].text)
    prerequisite = payload["context"]["prerequisiteCalls"][0]
    assert prerequisite["tool"] == "list-project-files"
    assert prerequisite["output"]["programPath"] == "/repo/scoped.exe"
    assert gate_manager.providers[-1].program_info is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_response_context_preserves_explicit_program_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain_file = SimpleNamespace(
        getPathname=lambda: "/repo/scoped.exe",
        getSharedProjectURL=lambda _ref: None,
        getProjectLocator=lambda: None,
    )
    scoped_info = SimpleNamespace(
        program=SimpleNamespace(getDomainFile=lambda: domain_file),
        file_path="/repo/scoped.exe",
    )
    provider = _GateProbeProvider()
    monkeypatch.setattr(
        program_metadata_module,
        "collect_project_context",
        lambda _session_id: {"activeProgram": "/repo/session.exe"},
    )

    scoped_result = await provider.call_tool("scope-error", {}, program_info=scoped_info)
    none_result = await provider.call_tool("scope-error", {}, program_info=None)
    fallback_result = await provider.call_tool("scope-error", {})

    scoped_context = json.loads(scoped_result[0].text)["projectContext"]
    assert scoped_context["scope"] == "target-program"
    assert scoped_context["activeProgram"] == "/repo/scoped.exe"
    assert "projectContext" not in json.loads(none_result[0].text)
    assert json.loads(fallback_result[0].text)["projectContext"]["activeProgram"] == "/repo/session.exe"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analysis_gate_invoked_for_non_exempt_tool(
    gate_manager: ToolProviderManager,
    program_info: SimpleNamespace,
) -> None:
    gate_threads = []
    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_program_info",
            return_value=program_info,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=None,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_utils.program_analysis.wait_for_program_analysis_ready",
            side_effect=lambda *_args, **_kwargs: gate_threads.append(threading.get_ident()),
        ) as gate_wait,
        patch("agentdecompile_cli.mcp_server.tool_providers.analysis_skipped_warning", return_value=None),
    ):
        await asyncio.wait_for(
            gate_manager.call_tool("list-functions", {"programPath": "/repo/other.exe"}),
            timeout=3,
        )

    gate_wait.assert_called_once_with(
        program_info.program, program_info, program_path="/repo/other.exe",
    )
    assert len(gate_threads) == 1
    assert gate_threads[0] != threading.get_ident()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analysis_gate_skipped_for_exempt_list_project_files(
    gate_manager: ToolProviderManager,
) -> None:
    to_thread_mock = AsyncMock(return_value=None)
    with (
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.asyncio.to_thread",
            to_thread_mock,
        ),
    ):
        await gate_manager.call_tool("list-project-files", {})

    to_thread_mock.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analysis_gate_skipped_for_exempt_checkout_program(
    gate_manager: ToolProviderManager,
    program_info: SimpleNamespace,
) -> None:
    to_thread_mock = AsyncMock(return_value=None)
    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_program_info",
            return_value=program_info,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=program_info,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.asyncio.to_thread",
            to_thread_mock,
        ),
    ):
        await gate_manager.call_tool("checkout-program", {"programPath": "/repo/other.exe"})

    to_thread_mock.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analysis_gate_skipped_for_autoprereq_invocation(
    gate_manager: ToolProviderManager,
    program_info: SimpleNamespace,
) -> None:
    to_thread_mock = AsyncMock(return_value=None)
    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_program_info",
            return_value=program_info,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=None,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.asyncio.to_thread",
            to_thread_mock,
        ),
    ):
        await gate_manager.call_tool(
            "list-functions",
            {"programPath": "/repo/other.exe", "__auto_prereq_invocation": True},
        )

    to_thread_mock.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analysis_incomplete_returns_structured_error(
    gate_manager: ToolProviderManager,
    program_info: SimpleNamespace,
) -> None:
    async def _raise_incomplete(*_args, **_kwargs):
        raise ProgramAnalysisTimeout("Ghidra auto-analysis did not complete for program (key=/repo/other.exe)")

    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_program_info",
            return_value=program_info,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=None,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.asyncio.to_thread",
            side_effect=_raise_incomplete,
        ),
    ):
        result = await gate_manager.call_tool(
            "list-functions",
            {"programPath": "/repo/other.exe", "responseFormat": "json"},
        )

    assert len(result) == 1
    assert "analysis-timeout" in result[0].text
    assert "did not complete" in result[0].text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analysis_timeout_returns_structured_error(
    gate_manager: ToolProviderManager,
    program_info: SimpleNamespace,
) -> None:
    lifecycle_info = SimpleNamespace(program=MagicMock(), file_path="/repo/lifecycle.exe")
    gate_manager.set_program_info(lifecycle_info)

    async def _raise_timeout(*_args, **_kwargs):
        raise ProgramAnalysisTimeout("Ghidra analysis did not finish within 600s")

    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_program_info",
            return_value=program_info,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=None,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.asyncio.to_thread",
            side_effect=_raise_timeout,
        ),
    ):
        result = await gate_manager.call_tool(
            "list-functions",
            {"programPath": "/repo/other.exe", "responseFormat": "json"},
        )

    assert len(result) == 1
    assert "analysis-timeout" in result[0].text
    assert "600s" in result[0].text
    assert gate_manager.program_info is lifecycle_info
    assert gate_manager.providers[-1].program_info is lifecycle_info


@pytest.mark.unit
@pytest.mark.asyncio
async def test_requested_program_path_does_not_fallback_to_active_program(
    gate_manager: ToolProviderManager,
) -> None:
    active_info = SimpleNamespace(program=MagicMock(), ghidra_analysis_complete=False)
    to_thread_mock = AsyncMock(return_value=None)
    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_program_info",
            return_value=None,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=active_info,
        ),
        patch.object(gate_manager, "_activate_requested_program", AsyncMock(return_value=None)),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.asyncio.to_thread",
            to_thread_mock,
        ),
    ):
        result = await gate_manager.call_tool(
            "list-functions",
            {"programPath": "/repo/missing.exe", "responseFormat": "json"},
        )

    assert "program-resolution-failed" in result[0].text
    to_thread_mock.assert_not_awaited()


@pytest.mark.unit
def test_analysis_timeout_error_response_json_contract() -> None:
    exc = ProgramAnalysisTimeout("Ghidra analysis did not finish within 600s")
    result = analysis_timeout_error_response(exc, "/repo/sample.exe")
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert payload["context"]["state"] == "analysis-timeout"
    assert payload["context"]["programPath"] == "/repo/sample.exe"
    assert "nextSteps" in payload


@pytest.mark.unit
def test_analysis_timeout_error_response_empty_program_path() -> None:
    exc = ProgramAnalysisTimeout("timed out")
    payload = json.loads(analysis_timeout_error_response(exc, None)[0].text)
    assert payload["context"]["programPath"] == ""


@pytest.mark.unit
def test_resolve_domain_program_path_prefers_domain_file_pathname() -> None:
    program = MagicMock()
    program.getDomainFile.return_value.getPathname.return_value = "/repo/foo.exe"
    assert resolve_domain_program_path(program, "/fallback.exe") == "/repo/foo.exe"


@pytest.mark.unit
def test_resolve_domain_program_path_uses_fallback_when_pathname_empty() -> None:
    program = MagicMock()
    program.getDomainFile.return_value.getPathname.return_value = "   "
    assert resolve_domain_program_path(program, "/fallback.exe") == "/fallback.exe"


@pytest.mark.unit
def test_resolve_domain_program_path_uses_fallback_when_no_domain_file() -> None:
    program = MagicMock()
    program.getDomainFile.return_value = None
    assert resolve_domain_program_path(program, "/fallback.exe") == "/fallback.exe"


@pytest.mark.unit
def test_resolve_domain_program_path_uses_fallback_on_get_domain_file_error() -> None:
    program = MagicMock()
    program.getDomainFile.side_effect = RuntimeError("no domain file")
    assert resolve_domain_program_path(program, "/fallback.exe") == "/fallback.exe"


@pytest.mark.unit
def test_resolve_domain_program_path_returns_none_when_no_path_available() -> None:
    program = MagicMock()
    program.getDomainFile.return_value = None
    assert resolve_domain_program_path(program, None) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_provider_analysis_timeout_returns_structured_error(
    gate_manager: ToolProviderManager,
) -> None:
    """Exempt tools skip the gate; handler-raised ProgramAnalysisTimeout maps to analysis-timeout."""

    with patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"):
        result = await gate_manager.call_tool(
            "open",
            {"path": "/tmp/sample.exe", "responseFormat": "json"},
        )

    assert len(result) == 1
    assert "analysis-timeout" in result[0].text
    assert "did not complete" in result[0].text
