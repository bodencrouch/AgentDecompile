"""Regression: a successful enableVersionControl=True import must attach projectContext
for the program it just created, the same way the default (non-versioned) import path
reassigns program_info to the last-imported program before calling create_success_response.

After 14af673 restored the call-scoped projectContext contract (the manager no longer
falls back to session-wide context on the success path), the versioned/shared import
branches in ImportExportToolProvider._handle_import passed the incoming (often None)
program_info straight through to create_success_response, so a successful versioned
import returned no projectContext at all.
"""

from __future__ import annotations

import json

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_cli.mcp_server import tool_providers as tool_providers_module
from agentdecompile_cli.mcp_server.providers import import_export as import_export_module
from agentdecompile_cli.mcp_server.providers.import_export import ImportExportToolProvider
from agentdecompile_cli.mcp_server.session_context import SESSION_CONTEXTS


def _shared_server_handle() -> dict[str, object]:
    return {
        "mode": "shared-server",
        "server_host": "127.0.0.1",
        "server_port": 26100,
        "repository_name": "agentrepo",
        "repository_adapter": object(),
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_versioned_file_import_attaches_imported_program_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = "test-versioned-file-import-context"
    SESSION_CONTEXTS.set_project_handle(session_id, _shared_server_handle())
    monkeypatch.setattr(import_export_module, "get_current_mcp_session_id", lambda: session_id)
    monkeypatch.setattr(tool_providers_module, "get_current_mcp_session_id", lambda: session_id)

    binary = tmp_path / "sample.bin"
    binary.write_bytes(b"\x90" * 64)

    provider = ImportExportToolProvider()
    provider._manager = SimpleNamespace(ghidra_project=None)

    def fake_shared_import(source, recursive, analyze_after_import, *, program_file_name=None, program_info=None):
        return {
            "action": "import",
            "importedFrom": str(source),
            "importedPrograms": [{"sourcePath": str(source), "programName": program_file_name or "sample.bin"}],
            "success": True,
            "versionControlRequested": True,
            "versionControlEnabled": True,
        }

    monkeypatch.setattr(provider, "_handle_shared_import", fake_shared_import)

    result = await provider._handle_import(
        {"path": str(binary), "enableversioncontrol": True, "programname": "sample.bin"},
        program_info=None,
    )
    payload = json.loads(result[0].text)

    assert payload["success"] is True, payload
    ctx = payload.get("projectContext")
    assert ctx is not None, payload
    assert ctx["scope"] == "target-program"
    assert ctx["activeProgram"] == "/sample.bin"
    assert ctx["mode"] == "shared-server"
    assert ctx["serverHost"] == "127.0.0.1"
    assert ctx["serverPort"] == 26100
    assert ctx["repository"] == "agentrepo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_versioned_folder_import_attaches_imported_program_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = "test-versioned-folder-import-context"
    SESSION_CONTEXTS.set_project_handle(session_id, _shared_server_handle())
    monkeypatch.setattr(import_export_module, "get_current_mcp_session_id", lambda: session_id)
    monkeypatch.setattr(tool_providers_module, "get_current_mcp_session_id", lambda: session_id)

    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"\x90" * 64)

    provider = ImportExportToolProvider()
    provider._manager = SimpleNamespace(ghidra_project=None)

    def fake_shared_import(source, recursive, analyze_after_import, *, program_file_name=None, program_info=None):
        return {
            "action": "import",
            "importedFrom": str(source),
            "importedPrograms": [{"sourcePath": str(source / "a.bin"), "programName": "a.bin"}],
            "success": True,
            "versionControlRequested": True,
            "versionControlEnabled": True,
        }

    monkeypatch.setattr(provider, "_handle_shared_import", fake_shared_import)

    result = await provider._handle_import(
        {"path": str(folder), "enableversioncontrol": True},
        program_info=None,
    )
    payload = json.loads(result[0].text)

    assert payload["success"] is True, payload
    ctx = payload.get("projectContext")
    assert ctx is not None, payload
    assert ctx["scope"] == "target-program"
    assert ctx["activeProgram"] == "/a.bin"
    assert ctx["mode"] == "shared-server"
    assert ctx["repository"] == "agentrepo"
