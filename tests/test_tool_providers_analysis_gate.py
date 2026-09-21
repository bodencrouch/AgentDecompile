"""Unit tests for ToolProviderManager pre-dispatch analysis gate."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp import types

from agentdecompile_cli.mcp_server.tool_providers import (
    ToolProvider,
    ToolProviderManager,
    analysis_timeout_error_response,
    create_success_response,
    resolve_domain_program_path,
)
from agentdecompile_cli.mcp_utils.program_analysis import ProgramAnalysisTimeout


class _GateProbeProvider(ToolProvider):
    """Minimal provider for list-functions, list-project-files, and open."""

    HANDLERS = {
        "checkoutprogram": "_handle_probe",
        "listfunctions": "_handle_probe",
        "listprojectfiles": "_handle_probe",
        "open": "_handle_open",
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
        ]

    async def _handle_open(self, _args: dict):
        raise ProgramAnalysisTimeout("Ghidra auto-analysis did not complete during open")

    async def _handle_probe(self, _args: dict, *, program_info: SimpleNamespace | None):
        return create_success_response(
            {
                "ok": True,
                "programPath": str(getattr(program_info, "file_path", "")),
                "programName": str(getattr(program_info, "name", "")),
            }
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
    return SimpleNamespace(
        program=program,
        ghidra_analysis_complete=False,
        file_path="/repo/other.exe",
        name="other.exe",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_program_context_is_call_scoped_across_analysis_gate_interleaving(
    gate_manager: ToolProviderManager,
) -> None:
    def _program_info(path: str) -> SimpleNamespace:
        program = MagicMock()
        program.getDomainFile.return_value.getPathname.return_value = path
        return SimpleNamespace(
            program=program,
            ghidra_analysis_complete=False,
            file_path=path,
            name=path.rsplit("/", 1)[-1],
        )

    lifecycle_info = _program_info("/repo/lifecycle.exe")
    program_a = _program_info("/repo/a.exe")
    program_b = _program_info("/repo/b.exe")
    gate_manager.set_program_info(lifecycle_info)
    provider = gate_manager._tool_map["listfunctions"]

    a_waiting = asyncio.Event()
    release_a = asyncio.Event()

    async def _interleave_at_gate(_wait_fn, _program, info, **_kwargs):
        if info is program_a:
            a_waiting.set()
            await release_a.wait()

    def _lookup(_session_id: str, path: str | None = None):
        return {"/repo/a.exe": program_a, "/repo/b.exe": program_b}.get(path)

    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_program_info",
            side_effect=_lookup,
        ),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=None,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.asyncio.to_thread",
            side_effect=_interleave_at_gate,
        ),
    ):
        call_a = asyncio.create_task(
            gate_manager.call_tool(
                "list-functions",
                {"programPath": "/repo/a.exe", "responseFormat": "json"},
            )
        )
        await a_waiting.wait()
        result_b = await gate_manager.call_tool(
            "list-functions",
            {"programPath": "/repo/b.exe", "responseFormat": "json"},
        )
        release_a.set()
        result_a = await call_a

    assert json.loads(result_a[0].text)["programPath"] == "/repo/a.exe"
    assert json.loads(result_b[0].text)["programPath"] == "/repo/b.exe"
    assert provider.program_info is lifecycle_info


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_provider_call_uses_lifecycle_program_fallback(
    program_info: SimpleNamespace,
) -> None:
    provider = _GateProbeProvider(program_info)

    result = await provider.call_tool(
        "list-functions",
        {"programPath": "/repo/other.exe", "responseFormat": "json"},
    )

    assert json.loads(result[0].text)["programPath"] == "/repo/other.exe"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_explicit_none_does_not_use_provider_lifecycle_program(
    program_info: SimpleNamespace,
) -> None:
    provider = _GateProbeProvider(program_info)

    result = await provider.call_tool(
        "list-functions",
        {"programPath": "/repo/other.exe", "responseFormat": "json"},
        program_info=None,
    )

    assert json.loads(result[0].text)["programPath"] == ""
    assert provider.program_info is program_info


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manager_explicit_none_does_not_use_session_or_lifecycle_program(
    gate_manager: ToolProviderManager,
    program_info: SimpleNamespace,
) -> None:
    gate_manager.set_program_info(program_info)
    with (
        patch(
            "agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.get_active_program_info",
            return_value=program_info,
        ),
        patch("agentdecompile_cli.mcp_server.tool_providers.SESSION_CONTEXTS.add_tool_history"),
    ):
        result = await gate_manager.call_tool(
            "list-functions",
            {"responseFormat": "json"},
            program_info=None,
        )

    assert json.loads(result[0].text)["programPath"] == ""
    assert gate_manager.program_info is program_info
    assert gate_manager._tool_map["listfunctions"].program_info is program_info


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analysis_gate_invoked_for_non_exempt_tool(
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
        await gate_manager.call_tool("list-functions", {"programPath": "/repo/other.exe"})

    assert to_thread_mock.await_count == 1
    assert to_thread_mock.await_args.args[0].__name__ == "wait_for_program_analysis_ready"


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
