"""Regressions found by running every agentdecompile-cli command against a live local backend."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agentdecompile_cli.mcp_server.providers.project import ProjectToolProvider
from agentdecompile_cli.mcp_server.response_formatter import render_tool_response


def _fake_program() -> MagicMock:
    program = MagicMock()
    program.getName.return_value = "test_program"
    program.getDomainFile.return_value.getPathname.return_value = "/test_program"
    program.getLanguageID.return_value = "x86:LE:64:default"
    program.getCompilerSpec.return_value.getCompilerSpecID.return_value = "gcc"
    program.getImageBase.return_value = "00100000"
    program.getSymbolTable.return_value.getNumSymbols.return_value = 57
    return program


@pytest.mark.unit
def test_get_current_program_reports_path_image_base_and_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ProjectToolProvider.__new__(ProjectToolProvider)
    program = _fake_program()
    info = SimpleNamespace(program=program)

    async def _loaded(_args, *, program_info):
        return program_info

    monkeypatch.setattr(provider, "_ensure_program_loaded_for_stateless_request", _loaded, raising=False)
    fm = MagicMock()
    fm.getFunctionCount.return_value = 22
    monkeypatch.setattr(provider, "_get_function_manager", lambda *_a, **_k: fm, raising=False)

    result = asyncio.run(provider._handle_get_current_program({}, program_info=info))
    data = json.loads(result[0].text)

    assert data["programPath"] == "/test_program"
    assert data["imageBase"] == "00100000"
    assert data["symbolCount"] == 57
    assert data["functionCount"] == 22

    text = render_tool_response("getcurrentprogram", data)
    assert "**Path:** `/test_program`" in text
    assert "**Image Base:** `00100000`" in text
    assert "**Symbols:** 57" in text
