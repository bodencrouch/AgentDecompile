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


@pytest.mark.unit
def test_disassembly_bytes_are_unsigned_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    """Java byte[] arrives signed: MOV RBP,RSP printed as '48 -77 -1b'."""
    from agentdecompile_cli.mcp_server.providers.functions import FunctionToolProvider

    provider = FunctionToolProvider.__new__(FunctionToolProvider)
    instr = MagicMock()
    instr.getAddress.return_value = "0040115e"
    instr.getMnemonicString.return_value = "MOV"
    instr.__str__ = lambda _self: "MOV RBP,RSP"
    instr.getBytes.return_value = [0x48, -119, -27]
    it = MagicMock()
    it.hasNext.side_effect = [True, False]
    it.next.return_value = instr
    listing = MagicMock()
    listing.getInstructions.return_value = it
    monkeypatch.setattr(provider, "_get_listing", lambda *_a, **_k: listing, raising=False)
    func = MagicMock()
    func.getName.return_value = "main"

    result = asyncio.run(provider._handle_disassemble({}, func, MagicMock(), 10, 30, program_info=None))
    data = json.loads(result[0].text)
    assert data["instructions"][0]["bytes"] == "48 89 e5"


@pytest.mark.unit
def test_callgraph_graph_renders_mermaid_text() -> None:
    """CallGraphTool returns Mermaid text; the renderer dropped it and printed only a header."""
    flow = "flowchart TD\n  a[add] --> b[main]"
    text = render_tool_response("getcallgraph", {"functionName": "add-00401136", "direction": "calling", "graph": flow})
    assert "```mermaid" in text
    assert "a[add] --> b[main]" in text

    empty = render_tool_response("getcallgraph", {"functionName": "main-0040115d", "direction": "calling", "graph": ""})
    assert "No call relationships" in empty


class _SymAddr:
    def __init__(self, offset: int) -> None:
        self.offset = offset


class _SymProgram:
    """Minimal program: default space builds addresses; one symbol named 'add'."""

    def __init__(self, symbols: dict[str, int]) -> None:
        self._symbols = symbols

    def getAddressFactory(self):
        space = SimpleNamespace(getAddress=lambda off: _SymAddr(int(off)))
        return SimpleNamespace(getDefaultAddressSpace=lambda: space)

    def getSymbolTable(self):
        def by_name(name, _ns):
            if name in self._symbols:
                return [SimpleNamespace(getAddress=lambda: _SymAddr(self._symbols[name]))]
            return []

        return SimpleNamespace(getLabelOrFunctionSymbols=by_name, getSymbols=lambda _n: [])


@pytest.mark.unit
def test_hex_looking_symbol_name_resolves_to_the_symbol() -> None:
    """Live: `references to --target add` resolved to address 0x00000add, not function add."""
    from agentdecompile_cli.mcp_utils.address_util import AddressUtil

    prog = _SymProgram({"add": 0x401136})
    assert AddressUtil.resolve_address_or_symbol(prog, "add").offset == 0x401136
    # No symbol named "dead": still parsed as hex.
    assert AddressUtil.resolve_address_or_symbol(prog, "dead").offset == 0xDEAD
    # Digit-leading hex and 0x-prefixed stay address-first even if a symbol shares the text.
    prog2 = _SymProgram({"007b5000": 0x1})
    assert AddressUtil.resolve_address_or_symbol(prog2, "007b5000").offset == 0x007B5000
    assert AddressUtil.resolve_address_or_symbol(prog, "0xadd").offset == 0xADD


@pytest.mark.unit
def test_constants_count_every_hit_and_render_samples() -> None:
    """Live: `constants specific --value 5` printed rows with empty Address/Function/Mnemonic,
    and occurrences were capped at samples_per_constant."""
    from agentdecompile_cli.mcp_server.providers._collectors import collect_constants

    def instr(addr: str, value: int):
        scalar = SimpleNamespace(getValue=lambda: value)
        return SimpleNamespace(
            getNumOperands=lambda: 1,
            getOpObjects=lambda _i: [scalar],
            getAddress=lambda: addr,
            __str__=lambda: f"MOV EAX,{value:#x}",
        )

    instrs = [instr(f"0040{i:04x}", 5) for i in range(7)]
    it = iter(instrs)
    pending = list(instrs)
    iterator = SimpleNamespace(hasNext=lambda: bool(pending), next=lambda: (pending.pop(0), next(it))[1])
    program = SimpleNamespace(getListing=lambda: SimpleNamespace(getInstructions=lambda _fwd: iterator))

    results, scanned = collect_constants(program, value_filter=lambda v: v == 5, samples_per_constant=3)
    assert scanned == 7
    assert results[0]["occurrences"] == 7
    assert len(results[0]["samples"]) == 3

    text = render_tool_response("searchconstants", {"mode": "specific", "results": results, "instructionsScanned": 7})
    assert "| 5 | 0x5 | 7 |" in text
    assert "`00400000`" in text
