"""CLI status shorthand must not invent a recovery directory or mask failures."""
from __future__ import annotations

import json

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from agentdecompile_cli import cli
from click.testing import CliRunner

pytestmark = pytest.mark.unit


def envelope(data):
    return {"content": [{"type": "text", "text": json.dumps(data)}], "isError": False}


@pytest.fixture
def backend(monkeypatch):
    client = object()

    @asynccontextmanager
    async def connected(_ctx):
        yield client

    execute = AsyncMock(return_value=envelope({"files": [], "count": 0}))
    monkeypatch.setattr(cli, "_tool_sequence_client", connected)
    monkeypatch.setattr(cli, "_execute_tool_call", execute)
    monkeypatch.setattr(cli, "_load_cli_state", dict)
    return execute, client


def test_original_empty_status_sequence_succeeds_and_runs_second_step(backend):
    execute, client = backend
    steps = '[{"name":"status","arguments":{}},{"name":"list-project-files","arguments":{}}]'
    result = CliRunner().invoke(cli.main, ["--server-url", "http://127.0.0.1:8080", "-f", "json", "tool-seq", steps])
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["success"] is True
    assert len(output["steps"]) == 2
    status = output["steps"][0]["result"]
    assert status["scope"] == "connection-session"
    assert status["recoveryWorkspaceInspected"] is False
    assert status["projectFiles"]["count"] == 0
    assert output["steps"][1]["success"] is True
    assert [call.args[1] for call in execute.await_args_list] == ["list_project_files", "list_project_files"]
    assert all(call.args[3] is client for call in execute.await_args_list)


@pytest.mark.parametrize("arguments", [{"workDir": "/explicit/run"}, {"work_dir": "/explicit/run"}, {"workDir": ""}, {"typo": "somewhere"}])
def test_explicit_recovery_or_invalid_arguments_keep_original_routing(backend, arguments):
    execute, _ = backend
    result = CliRunner().invoke(cli.main, ["tool", "status", json.dumps(arguments)])
    assert result.exit_code == 0, result.output
    assert execute.await_count == 1
    assert execute.await_args.args[1] == "status"
    expected = {"workDir": arguments["work_dir"]} if "work_dir" in arguments else arguments
    assert all(execute.await_args.args[2][key] == value for key, value in expected.items())


@pytest.mark.parametrize("response", [
    {"isError": True, "content": [{"type": "text", "text": "connection failed"}]},
    envelope({"success": False, "error": "Project unavailable"}),
    {"content": [{"type": "text", "text": "## Error\n\n> **Project unavailable**"}]},
])
def test_failed_session_read_still_stops_the_sequence(backend, response):
    execute, _ = backend
    execute.return_value = response
    result = CliRunner().invoke(cli.main, ["tool-seq", '[{"name":"status"},{"name":"list-project-files"}]'])
    assert result.exit_code == 1
    assert execute.await_count == 1
    assert "Sequence failed" in result.output
    assert "Read-only project listing succeeded" not in result.output


@pytest.mark.parametrize("command", [["status"], ["tool", "STATUS", "{}"], ["tool", "status", '{"responseFormat":"json"}']])
def test_direct_and_generic_status_share_the_no_workspace_shorthand(backend, command):
    execute, _ = backend
    result = CliRunner().invoke(cli.main, command)
    assert result.exit_code == 0, result.output
    assert execute.await_args.args[1] == "list_project_files"
    assert "connection-session" in result.output or "Connection / session status" in result.output


def test_status_help_explains_both_scopes_without_contacting_a_backend(backend):
    execute, _ = backend
    result = CliRunner().invoke(cli.main, ["status", "--help"])
    assert result.exit_code == 0, result.output
    assert "connection/session" in result.output
    assert "--work_dir" in result.output
    assert "MCP status tool itself requires workDir" in result.output
    execute.assert_not_awaited()
