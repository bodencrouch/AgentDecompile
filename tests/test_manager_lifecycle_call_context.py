"""Manager activation retains the context returned by shared checkout."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agentdecompile_cli.mcp_server import tool_providers


@pytest.mark.asyncio
@pytest.mark.parametrize("bootstrap", [False, True])
async def test_activation_retains_checkout_context(monkeypatch, bootstrap):
    manager = tool_providers.ToolProviderManager()
    target = SimpleNamespace(program=object(), name="A")
    lifecycle = SimpleNamespace(program=object(), name="B")
    manager.program_info = lifecycle
    adapter = object()
    handle = {"repository_adapter": adapter}
    session = SimpleNamespace(project_handle=None if bootstrap else handle)
    opened = []

    async def open_project(args, *, program_info):
        assert program_info is None
        assert args["shared"] is True
        opened.append(args)
        session.project_handle = handle
        return []

    async def checkout(repository_adapter, path, session_id, *, program_info):
        assert program_info is None
        assert (repository_adapter, path, session_id) == (adapter, "/A", "test-session")
        # A concurrent activation may change lifecycle state before this return.
        manager.set_program_info(lifecycle)
        return target

    provider = SimpleNamespace(_handle_open_project=open_project, _checkout_shared_program=checkout)
    monkeypatch.setattr(manager, "_get_project_provider", lambda: provider)
    monkeypatch.setattr(manager, "_activate_local_program_by_path", lambda *_: pytest.fail("Unexpected local fallback"))
    monkeypatch.setattr(tool_providers.SESSION_CONTEXTS, "get_program_info", lambda *_: None)
    monkeypatch.setattr(tool_providers.SESSION_CONTEXTS, "get_or_create", lambda *_: session)
    monkeypatch.setattr(tool_providers, "is_shared_server_handle", lambda value: value is handle)
    monkeypatch.setattr("agentdecompile_cli.mcp_server.auth.get_current_auth_context", lambda: None)
    monkeypatch.setenv("AGENT_DECOMPILE_GHIDRA_SERVER_HOST", "test-host")
    monkeypatch.setenv("AGENT_DECOMPILE_GHIDRA_SERVER_REPOSITORY", "test-repo")

    assert await manager._activate_requested_program("test-session", "/A") is target
    assert manager.program_info is lifecycle
    assert len(opened) == int(bootstrap)


@pytest.mark.asyncio
async def test_failed_checkout_keeps_local_activation_fallback(monkeypatch):
    manager = tool_providers.ToolProviderManager()
    target = SimpleNamespace(program=object())
    checkout = AsyncMock(side_effect=RuntimeError("checkout unavailable"))
    adapter = object()
    session = SimpleNamespace(project_handle={"repository_adapter": adapter})
    monkeypatch.setattr(manager, "_get_project_provider", lambda: SimpleNamespace(_checkout_shared_program=checkout))
    monkeypatch.setattr(tool_providers.SESSION_CONTEXTS, "get_program_info", lambda *_: None)
    monkeypatch.setattr(tool_providers.SESSION_CONTEXTS, "get_or_create", lambda *_: session)
    monkeypatch.setattr(tool_providers, "is_shared_server_handle", lambda _: True)
    bootstrap = AsyncMock(return_value=None)
    monkeypatch.setattr(manager, "_bootstrap_shared_session_from_env", bootstrap)
    local_open = Mock(return_value=target)
    monkeypatch.setattr(manager, "_activate_local_program_by_path", local_open)

    assert await manager._activate_requested_program("test-session", "/A") is target
    checkout.assert_awaited_once_with(adapter, "/A", "test-session", program_info=None)
    bootstrap.assert_awaited_once_with("test-session", "/A")
    local_open.assert_called_once_with("test-session", "/A")
