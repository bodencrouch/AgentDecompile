"""Real provider dispatch must use the requested context, including nested modes."""

from __future__ import annotations

import json
import sys

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from agentdecompile_cli.mcp_server.providers import (
    BookmarkToolProvider,
    CommentToolProvider,
    ConstantSearchToolProvider,
    CrossReferencesToolProvider,
    DataFlowToolProvider,
    DataToolProvider,
    DataTypeToolProvider,
    DecompilerToolProvider,
    EnumToolProvider,
    FunctionToolProvider,
    GetFunctionAioToolProvider,
    GetFunctionToolProvider,
    MemoryToolProvider,
    StringToolProvider,
    StructureToolProvider,
    SymbolToolProvider,
    VtableToolProvider,
    decompiler as decompiler_module,
    functions as functions_module,
)
from agentdecompile_cli.mcp_server.providers._program_context import ghidra_tools_for_program
from agentdecompile_cli.mcp_utils.address_util import AddressUtil


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_type", [
    BookmarkToolProvider, CommentToolProvider, ConstantSearchToolProvider,
    CrossReferencesToolProvider, DataFlowToolProvider, DataToolProvider,
    DataTypeToolProvider, DecompilerToolProvider, EnumToolProvider,
    FunctionToolProvider, GetFunctionAioToolProvider, GetFunctionToolProvider,
    MemoryToolProvider, StringToolProvider, StructureToolProvider,
    SymbolToolProvider, VtableToolProvider,
])
async def test_explicit_none_never_borrows_lifecycle_program(provider_type):
    provider = provider_type()
    lifecycle = SimpleNamespace(program=object())
    provider.program_info = lifecycle
    tool = "manage-symbols" if provider_type is SymbolToolProvider else next(iter(provider.HANDLERS))
    response = await provider.call_tool(tool, {"format": "json"}, program_info=None)
    payload = json.loads(response[0].text)
    assert payload["success"] is False
    assert "No program loaded" in response[0].text
    assert provider.program_info is lifecycle


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider_type", "tool", "args"), [
    (StringToolProvider, "list-strings", {}),
    (StringToolProvider, "search-code", {"query": "program"}),
    (SymbolToolProvider, "search-symbols", {"query": "program"}),
    (SymbolToolProvider, "manage-symbols", {"mode": "symbols"}),
    (SymbolToolProvider, "list-imports", {}),
    (SymbolToolProvider, "list-exports", {}),
])
async def test_wrappers_are_constructed_for_the_call(provider_type, tool, args, monkeypatch):
    target = SimpleNamespace(program=object())
    constructed = []

    class Wrapper:
        def __init__(self, program_info):
            constructed.append(program_info)

        def rows(self, *args, **kwargs):
            return [{"name": "program-A", "value": "program-A", "address": "1000"}]

        get_all_strings = search_code = search_symbols_by_name = get_all_symbols = list_imports = list_exports = rows

    monkeypatch.setitem(sys.modules, "agentdecompile_cli.tools.wrappers", SimpleNamespace(GhidraTools=Wrapper))
    provider = provider_type()
    lifecycle = SimpleNamespace(program=object())
    provider.program_info = lifecycle
    old_wrapper = object()
    provider.ghidra_tools = old_wrapper
    response = await provider.call_tool(tool, {**args, "format": "json"}, program_info=target)
    assert "program-A" in response[0].text
    assert constructed == [target]
    assert provider.program_info is lifecycle
    assert provider.ghidra_tools is old_wrapper


def test_unavailable_wrapper_preserves_direct_api_fallback(monkeypatch):
    def unavailable(program_info):
        raise RuntimeError("Optional backend unavailable")

    monkeypatch.setitem(sys.modules, "agentdecompile_cli.tools.wrappers", SimpleNamespace(GhidraTools=unavailable))
    assert ghidra_tools_for_program(SimpleNamespace(program=object())) is None
    assert ghidra_tools_for_program(None) is None


@pytest.mark.asyncio
async def test_datatype_nested_dispatch_uses_target_program():
    category = SimpleNamespace(getName=lambda: "program-A", getCategoryPath=lambda: "/program-A")
    root = SimpleNamespace(getCategories=lambda: [category], getDataTypes=list)
    target = SimpleNamespace(program=SimpleNamespace(getDataTypeManager=lambda: SimpleNamespace(getRootCategory=lambda: root)))
    provider = DataTypeToolProvider()
    provider.program_info = SimpleNamespace(program=object())
    response = await provider.call_tool("manage-data-types", {"mode": "list", "format": "json"}, program_info=target)
    assert json.loads(response[0].text)["results"] == [{"name": "program-A", "path": "/program-A", "isCategory": True}]


@pytest.mark.asyncio
async def test_function_listing_uses_target_program(monkeypatch):
    target = SimpleNamespace(program=SimpleNamespace(getFunctionManager=lambda: None))
    seen = []

    def collect(program, **_kwargs):
        seen.append(program)
        return [{"name": "program-A", "address": "1000", "size": 4, "isExternal": False,
                 "isThunk": False, "parameterCount": 0, "signature": "void programA()", "callingConvention": "cdecl"}]

    monkeypatch.setattr(functions_module, "collect_functions", collect)
    provider = FunctionToolProvider()
    provider.program_info = SimpleNamespace(program=object())
    response = await provider.call_tool("list-functions", {"format": "json"}, program_info=target)
    assert "program-A" in response[0].text
    assert seen == [target.program]


@pytest.mark.asyncio
async def test_comment_mutation_keeps_context_after_lifecycle_change(monkeypatch):
    writes = []
    transactions = []
    listing = SimpleNamespace(getComment=lambda *args: None, setComment=lambda *args: writes.append(args))
    program = SimpleNamespace(
        getListing=lambda: listing,
        startTransaction=lambda label: transactions.append(label) or 7,
        endTransaction=lambda tx, commit: transactions.append((tx, commit)),
    )
    target = SimpleNamespace(program=program)
    lifecycle = SimpleNamespace(program=object())
    provider = CommentToolProvider()
    provider.program_info = target

    def resolve(current_program, value):
        assert current_program is program
        provider.program_info = lifecycle
        return "1000"

    monkeypatch.setattr(AddressUtil, "resolve_address_or_symbol_prefer_thunk", resolve)
    response = await provider.call_tool("manage-comments", {"mode": "set", "address": "1000", "comment": "program-A", "format": "json"}, program_info=target)
    assert json.loads(response[0].text)["success"] is True
    assert writes == [("1000", 0, "program-A")]
    assert transactions == ["set-comment", (7, True)]
    assert provider.program_info is lifecycle


@pytest.mark.asyncio
async def test_decompiler_pipeline_uses_scoped_session_decompiler(monkeypatch):
    program = object()
    func = SimpleNamespace(getName=lambda: "programA", getEntryPoint=lambda: "1000")
    decompiled = SimpleNamespace(getC=lambda: "void programA() {}", getSignature=lambda: "void programA()")
    results = SimpleNamespace(decompileCompleted=lambda: True, getDecompiledFunction=lambda: decompiled)
    decompiler = SimpleNamespace(decompileFunction=lambda *args: results)
    target = SimpleNamespace(program=program, decompiler=decompiler)
    provider = DecompilerToolProvider()
    provider.program_info = SimpleNamespace(program=object(), decompiler=object())
    seen = []

    def acquire(session_decompiler, current_program):
        seen.append((session_decompiler, current_program))
        return nullcontext(SimpleNamespace(decompiler=session_decompiler))

    monkeypatch.setitem(sys.modules, "ghidra.util.task", SimpleNamespace(ConsoleTaskMonitor=lambda: object()))
    monkeypatch.setattr(decompiler_module, "acquire_decompiler_for_program", acquire)
    monkeypatch.setattr(provider, "_resolve_function", lambda *args, **kwargs: func)
    response = await provider.call_tool("decompile-function", {"function": "programA", "format": "json"}, program_info=target)
    assert json.loads(response[0].text)["code"] == "void programA() {}"
    assert seen == [(decompiler, program)]
