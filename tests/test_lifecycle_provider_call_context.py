"""Scoped dispatch through lifecycle, replay, and stateful provider seams."""

from __future__ import annotations

import ast
import asyncio
import json
import sys

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_cli.mcp_server.providers import conflict_resolution, import_export, project, search_everything
from agentdecompile_cli.mcp_server.providers.callgraph import CallGraphToolProvider
from agentdecompile_cli.mcp_server.providers.getfunction import GetFunctionToolProvider
from agentdecompile_cli.mcp_server.providers.script import ScriptToolProvider
from agentdecompile_cli.mcp_server.tool_providers import create_success_response


def info(name):
    program = SimpleNamespace(getName=lambda: name, getDomainFile=lambda: None)
    return SimpleNamespace(program=program, name=name, file_path=f"/{name}", decompiler=None, flat_api=None)


@pytest.mark.asyncio
async def test_graph_renderer_is_bound_to_each_call(monkeypatch):
    seen = []

    class Graph:
        def __init__(self, program_info):
            self.info = program_info
            seen.append(program_info)

        def generate_for_mcp(self, **kwargs):
            return SimpleNamespace(function_name=self.info.name, direction="calling", display_type="flow", graph={})

    monkeypatch.setitem(sys.modules, "agentdecompile_cli.tools.callgraph_tool", SimpleNamespace(CallGraphTool=Graph))
    provider = CallGraphToolProvider()
    provider.program_info = lifecycle = info("lifecycle")
    targets = [info("A"), info("B")]
    for target in targets:
        result = await provider.call_tool("get-call-graph", {"function": "main", "mode": "graph", "format": "json"}, program_info=target)
        assert json.loads(result[0].text)["functionName"] == target.name
        assert json.loads(result[0].text)["projectContext"]["activeProgram"] == target.name
    assert seen == targets
    assert provider.program_info is lifecycle


@pytest.mark.asyncio
@pytest.mark.parametrize("target_name", ["A", None])
async def test_script_namespace_never_borrows_lifecycle_context(target_name):
    provider = ScriptToolProvider()
    provider.program_info = lifecycle = info("B")
    target = info(target_name) if target_name else None
    if target is not None:
        for method in ("getMemory", "getListing", "getFunctionManager", "getSymbolTable", "getReferenceManager", "getDataTypeManager", "getLanguage", "getCompilerSpec", "getAddressFactory", "getBookmarkManager", "getEquateTable", "getExternalManager", "getRegister", "getProgramContext"):
            setattr(target.program, method, lambda *args: None)
    result = await provider.call_tool("execute-script", {
        "code": "currentProgram.getName() if currentProgram is not None else 'empty'", "format": "json",
    }, program_info=target)
    assert json.loads(result[0].text).get("result") == (target_name or "empty"), result[0].text
    assert provider.program_info is lifecycle


@pytest.mark.asyncio
async def test_search_fallback_uses_supplied_context_and_none_stays_empty(monkeypatch):
    provider = search_everything.SearchEverythingToolProvider()
    provider.program_info = info("B")
    monkeypatch.setattr(provider, "_collect_project_program_paths", lambda **kwargs: [])
    monkeypatch.setattr(search_everything.SESSION_CONTEXTS, "get_active_program_info", lambda *_: pytest.fail("Mutable active selection read"))
    target = info("A")
    targets, _, _ = await provider._resolve_target_programs({}, program_info=target)
    assert targets[0]["programInfo"] is target
    targets, _, _ = await provider._resolve_target_programs({}, program_info=None)
    assert targets == []


def test_search_strings_and_decompiler_use_only_the_target(monkeypatch):
    provider = search_everything.SearchEverythingToolProvider()
    provider.program_info = info("B")
    provider.program_info.decompiler = object()
    target = info("A")
    seen = []
    monkeypatch.setitem(sys.modules, "agentdecompile_cli.tools.wrappers", SimpleNamespace(GhidraTools=lambda context: seen.append(context) or context))
    monkeypatch.setattr(search_everything, "collect_strings", lambda program, **kwargs: [])
    provider._search_strings(target.program, ["value"], "auto", False, 0.7, {}, 10, program_info=target)
    assert seen == [target]

    monkeypatch.setitem(sys.modules, "ghidra.util.task", SimpleNamespace(ConsoleTaskMonitor=lambda: object()))
    monkeypatch.setattr(provider, "_get_function_manager", lambda *args, **kwargs: SimpleNamespace(getFunctions=lambda _: []))
    decompilers = []

    def acquire(decompiler, program):
        decompilers.append(decompiler)
        return nullcontext(SimpleNamespace(decompiler=object(), reused_session=False))

    monkeypatch.setattr("agentdecompile_cli.mcp_utils.decompiler_util.acquire_decompiler_for_program", acquire)
    _, diagnostic = provider._search_decompilation(target.program, None, ["value"], "auto", False, 0.7, {}, 10, 10, 1)
    assert diagnostic["scannedFunctions"] == 0
    assert decompilers == [None]


@pytest.mark.asyncio
async def test_conflict_replay_forwards_call_context(monkeypatch):
    target = info("A")
    provider = conflict_resolution.ConflictResolutionToolProvider()
    provider.program_info = info("B")
    pending = SimpleNamespace(tool="rename-function", arguments={"newName": "renamed"}, program_path="/A", conflict_id="conflict")
    monkeypatch.setattr(conflict_resolution, "conflict_get", lambda *_: pending)
    monkeypatch.setattr(conflict_resolution, "conflict_remove", lambda *_: None)

    async def replay(name, args, *, program_info):
        assert program_info is target
        assert args["programPath"] == "/A"
        assert args["__force_apply_conflict_id"] == "conflict"
        return create_success_response({"success": True})

    provider._manager = SimpleNamespace(call_tool=replay)
    result = await provider.call_tool("resolve-modification-conflict", {"conflictId": "conflict", "resolution": "overwrite", "format": "json"}, program_info=target)
    assert json.loads(result[0].text)["applied"] is True


@pytest.mark.asyncio
async def test_stateless_open_keeps_its_new_program_while_lifecycle_changes(monkeypatch):
    provider = project.ProjectToolProvider()
    target, other = info("A"), info("B")
    opened, resume = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(project.SESSION_CONTEXTS, "get_program_info", lambda session, key: target if key == "/A" else None)

    async def open_program(args, *, program_info):
        assert program_info is None
        opened.set()
        await resume.wait()
        return create_success_response({"success": True})

    monkeypatch.setattr(provider, "_handle_open_project", open_program)
    task = asyncio.create_task(provider.call_tool("get-current-program", {"programPath": "/A", "format": "json"}, program_info=None))
    await asyncio.wait_for(opened.wait(), 2)
    provider.set_program_info(other)
    result_b = await provider.call_tool("get-current-program", {"format": "json"}, program_info=other)
    resume.set()
    result_a = await asyncio.wait_for(task, 2)
    assert json.loads(result_a[0].text)["name"] == "A"
    assert json.loads(result_b[0].text)["name"] == "B"
    assert json.loads(result_a[0].text)["projectContext"]["activeProgram"] == "A"
    assert json.loads(result_b[0].text)["projectContext"]["activeProgram"] == "B"
    assert provider.program_info is other


@pytest.mark.asyncio
async def test_same_provider_prerequisite_recursion_carries_context(monkeypatch):
    provider = project.ProjectToolProvider()
    target = info("A")
    provider.program_info = info("B")
    monkeypatch.setattr(provider, "_get_shared_server_host", lambda: "")

    async def prerequisite(name, args, *, program_info):
        assert program_info is target
        return await provider.call_tool("get-current-program", {"format": "json"}, program_info=program_info)

    provider._manager = SimpleNamespace(call_tool=prerequisite)
    result = await asyncio.wait_for(provider.call_tool("open", {"format": "json"}, program_info=target), 2)
    assert json.loads(result[0].text)["name"] == "A"


@pytest.mark.asyncio
async def test_checkout_status_carries_the_context_returned_by_checkout(monkeypatch):
    provider = import_export.ImportExportToolProvider()
    project_provider = project.ProjectToolProvider()
    target, other = info("A"), info("B")
    provider.program_info = other
    domain_file = SimpleNamespace(isVersioned=lambda: True, isCheckedOut=lambda: True, canCheckout=lambda: False, canCheckin=lambda: True)
    calls = []

    def resolve(path, *, program_info):
        calls.append(program_info)
        return (domain_file, "A") if program_info is target else None

    async def checkout(*args, program_info, **kwargs):
        assert program_info is None
        return target

    monkeypatch.setattr(project_provider, "_checkout_shared_program", checkout)
    monkeypatch.setattr(provider, "_resolve_domain_file_for_checkout_status", resolve)
    handle = {"mode": "shared-server", "repository_adapter": object(), "server_host": "example", "repository_name": "test"}
    session = import_export.SessionContext(session_id="checkout-context", project_handle=handle)
    monkeypatch.setattr(import_export.SESSION_CONTEXTS, "get_or_create", lambda *_: session)
    provider._manager = SimpleNamespace(_get_project_provider=lambda: project_provider)
    result = await provider.call_tool("checkout-status", {"programPath": "/A", "format": "json"}, program_info=None)
    assert calls == [None, target], result[0].text
    assert json.loads(result[0].text)["program"] == "A"
    assert provider.program_info is other


def test_transaction_cleanup_does_not_scan_other_provider_contexts(monkeypatch):
    provider = import_export.ImportExportToolProvider()
    target, other = info("A"), info("B")
    provider.program_info = other

    class Manager:
        @property
        def providers(self):
            pytest.fail("Provider lifecycle contexts must not be scanned")

    provider._manager = Manager()
    seen = []
    monkeypatch.setattr(provider, "_end_nested_non_batch_transactions_on_program", seen.append)
    monkeypatch.setattr(import_export.SESSION_CONTEXTS, "get_or_create", lambda *_: SimpleNamespace(open_programs={}))
    provider._end_open_transactions_on_all_session_programs("session", program_info=target)
    assert seen and all(program is target.program for program in seen)


def test_activation_returns_context_and_preserves_lifecycle_fanout(monkeypatch):
    provider = project.ProjectToolProvider()
    program = info("A").program
    seen = []
    monkeypatch.setattr("agentdecompile_cli.mcp_utils.decompiler_util.open_decompiler_for_program", lambda _: None)
    monkeypatch.setattr("agentdecompile_cli.mcp_utils.program_analysis.program_needs_analysis", lambda _: False)
    monkeypatch.setattr(project.SESSION_CONTEXTS, "get_active_program_key", lambda _: None)
    monkeypatch.setattr(project.SESSION_CONTEXTS, "set_active_program_info", lambda session, path, context: seen.append(context))
    provider._manager = SimpleNamespace(set_program_info=seen.append)
    context = provider._set_active_program_info(program, "/A", analyze=False)
    assert context.program is program
    assert seen == [context, context]


def test_versioned_persistence_forwards_context_through_fallback(monkeypatch):
    provider = import_export.ImportExportToolProvider()
    target, other = info("A"), info("B")
    provider.program_info = other
    domain_file = SimpleNamespace(modifiedSinceCheckout=lambda: True)
    seen = []

    def persist(program, *, program_info):
        assert program is target.program
        seen.append(("persist", program_info))

    def dispose(session, domain_file, *, program_info):
        seen.append(("dispose", program_info))

    monkeypatch.setitem(sys.modules, "java.awt", None)
    monkeypatch.setattr(provider, "_persist_open_program_for_versioned_checkin", persist)
    monkeypatch.setattr(provider, "_dispose_decompilers_for_domain_file", dispose)
    monkeypatch.setattr(import_export.SESSION_CONTEXTS, "get_or_create", lambda *_: SimpleNamespace(open_programs={}))
    provider._save_domain_file_before_versioned_checkin(domain_file, target.program, program_info=target)
    assert seen == [("persist", target), ("dispose", target)]
    assert provider.program_info is other


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {"mode": "rename_variable", "variableMappings": "old:new"},
    {"mode": "set_variable_type", "datatypeMappings": "old:int"},
    {"mode": "set_variable_type", "variableName": "old", "newType": "int"},
    {"mode": "change_datatypes", "datatypeMappings": "old:int", "variableMappings": "old:new"},
])
async def test_variable_edit_modes_forward_context_to_checkout_notifier(arguments, monkeypatch):
    provider = GetFunctionToolProvider()
    target, other = info("A"), info("B")
    provider.program_info = other
    notified = []
    function = SimpleNamespace(getName=lambda: "entry")
    monkeypatch.setattr(provider, "_resolve_function", lambda *args, **kwargs: function)

    async def apply_edit(*args, program_info):
        assert program_info is target
        return {"success": True}

    def notify(program, program_path=None, *, program_info):
        assert program is target.program
        notified.append(program_info)

    monkeypatch.setattr(provider, "_apply_single_variable_rename", apply_edit)
    monkeypatch.setattr(provider, "_apply_single_variable_type", apply_edit)
    monkeypatch.setattr(provider, "_notify_versioned_checkout_after_program_edit", notify)
    response = await provider.call_tool("manage-function", {"function": "entry", "format": "json", **arguments}, program_info=target)
    assert json.loads(response[0].text)["success"] is True, response[0].text
    assert notified == [target]
    assert provider.program_info is other


def test_notifier_and_release_calls_forward_context_for_every_receiver_name():
    paths = Path(import_export.__file__).parent
    helpers = {"_notify_versioned_checkout_after_program_edit", "_release_session_programs_for_domain_file"}
    seen = set()
    for filename in ("getfunction.py", "import_export.py"):
        tree = ast.parse((paths / filename).read_text())
        for call in ast.walk(tree):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in helpers:
                seen.add(call.func.attr)
                assert any(keyword.arg == "program_info" and isinstance(keyword.value, ast.Name) and keyword.value.id == "program_info" for keyword in call.keywords), (filename, call.lineno)
    assert seen == helpers


@pytest.mark.asyncio
@pytest.mark.parametrize("incoming_name", ["A", None])
@pytest.mark.parametrize("open_kind", ["project-domain", "gpr-project"])
async def test_open_response_context_names_the_program_it_activated(incoming_name, open_kind, monkeypatch, tmp_path):
    provider = project.ProjectToolProvider()
    incoming = info(incoming_name) if incoming_name else None
    opened = info("B")
    provider.program_info = incoming
    monkeypatch.setattr(provider, "_get_shared_server_host", lambda: "")
    monkeypatch.setattr(provider, "_get_active_project_data", lambda **kwargs: SimpleNamespace(getFile=lambda _: object()))
    monkeypatch.setattr(provider, "_open_program_from_domain_file", lambda _: opened.program)
    monkeypatch.setattr("agentdecompile_cli.mcp_utils.decompiler_util.open_decompiler_for_program", lambda _: None)
    monkeypatch.setattr("agentdecompile_cli.mcp_utils.program_analysis.program_needs_analysis", lambda _: False)

    async def native_call(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("agentdecompile_cli.mcp_utils.async_native.native_call", native_call)
    monkeypatch.setattr(project.SESSION_CONTEXTS, "set_active_program_info", lambda *args: None)
    provider._manager = SimpleNamespace(set_program_info=provider.set_program_info)
    open_path = "/task4-response-context-B"
    if open_kind == "gpr-project":
        open_path = str(tmp_path / "B.gpr")
        project_data = SimpleNamespace(getRootFolder=lambda: object(), getFile=lambda _: object())
        ghidra_project = SimpleNamespace(getProject=lambda: SimpleNamespace(getProjectData=lambda: project_data))
        monkeypatch.setattr(provider, "_list_domain_files", lambda *args: [{"path": "/B", "name": "B", "type": "Program"}])
        monkeypatch.setattr(project.SESSION_CONTEXTS, "set_project_handle", lambda *args: None)
        monkeypatch.setattr(project.SESSION_CONTEXTS, "set_project_binaries", lambda *args: None)

        async def open_gpr(path, args):
            return await provider._set_gpr_project_state_and_respond(path, path.parent, path.stem, ghidra_project, args)

        monkeypatch.setattr(provider, "_create_and_open_gpr_project", open_gpr)
    response = await provider.call_tool("open", {"path": open_path, "analyzeAfterImport": False, "format": "json"}, program_info=incoming)
    payload = json.loads(response[0].text)
    assert payload["mode"] == open_kind, payload
    assert payload.get("projectContext", {}).get("activeProgram") == "B", payload
    assert provider.program_info.program is opened.program


def test_activated_response_preserves_success_when_metadata_is_unavailable(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr("agentdecompile_cli.mcp_server.tool_providers.attach_project_context_to_payload", unavailable)
    response = create_success_response({"success": True}, program_info=info("B"))
    payload = json.loads(response[0].text)
    assert payload["success"] is True
    assert payload["projectContext"]["activeProgram"] == "B"
    assert payload["projectContext"]["contextUnavailable"] == "metadata unavailable"
