from __future__ import annotations

import json
import sys

from types import SimpleNamespace
from typing import Any

import pytest

from agentdecompile_cli.mcp_server.providers.data import DataToolProvider
from agentdecompile_cli.mcp_utils.address_util import AddressUtil
from agentdecompile_cli.mcp_server.tool_providers import FORCE_APPLY_CONFLICT_ID_KEY


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_data_uses_java_byte_array_and_formats_returned_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allocated_lengths: list[int] = []
    java_buffer: list[int] = []

    def fake_jarray(component_type: object):
        assert component_type == "JByte"

        def allocate(length: int) -> list[int]:
            allocated_lengths.append(length)
            java_buffer.extend([0] * length)
            return java_buffer

        return allocate

    monkeypatch.setitem(sys.modules, "jpype", SimpleNamespace(JArray=fake_jarray, JByte="JByte"))

    class FakeMemory:
        def getBytes(self, address: object, output: list[int]) -> int:
            assert address == "100000520"
            assert output is java_buffer
            output[:5] = [0x52, 0x65, -86, 0x20, 0x7F]
            return 5

    provider = DataToolProvider()
    program = object()
    program_info = SimpleNamespace(program=program)
    monkeypatch.setattr(provider, "_require_program", lambda **_context: None)
    monkeypatch.setattr(AddressUtil, "resolve_address_or_symbol", lambda *_args: "100000520")
    monkeypatch.setattr(provider, "_resolve_address", lambda *_args, **_context: pytest.fail("Data reads must not redirect to a thunk"))
    monkeypatch.setattr(provider, "_get_memory", lambda *_args, **_context: FakeMemory())
    monkeypatch.setattr(
        provider,
        "_get_listing",
        lambda *_args, **_context: SimpleNamespace(getDataAt=lambda _address: None),
    )

    response = await provider._handle_get(
        {"addressorsymbol": "100000520", "length": 20000, "format": "both"},
        program_info=program_info,
    )
    payload: dict[str, Any] = json.loads(response[0].text)

    assert allocated_lengths == [10000]
    assert payload == {
        "address": "100000520",
        "length": 5,
        "hex": "52 65 aa 20 7f",
        "ascii": "Re. .",
    }


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("handler", ["_handle_get", "_handle_apply"])
async def test_unresolved_data_target_fails_before_java_access(monkeypatch, handler):
    provider = DataToolProvider()
    program = object()
    monkeypatch.setattr(AddressUtil, "resolve_address_or_symbol", lambda *_args: None)
    monkeypatch.setattr(provider, "_get_memory", lambda *_args, **_kw: pytest.fail("Unresolved target reached memory"))
    monkeypatch.setattr(provider, "_get_listing", lambda *_args, **_kw: pytest.fail("Unresolved target reached listing"))
    with pytest.raises(ValueError, match="Unable to resolve address or symbol: missing_symbol"):
        await getattr(provider, handler)(
            {"addressorsymbol": "missing_symbol", "datatype": "int"},
            program_info=SimpleNamespace(program=program),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_uses_exact_address_without_thunk_redirect(monkeypatch):
    provider = DataToolProvider()
    exact_address = SimpleNamespace(add=lambda offset: ("end", offset))
    data_type = SimpleNamespace(getLength=lambda: 4)
    type_manager = object()
    program = SimpleNamespace(getDataTypeManager=lambda: type_manager)
    seen = []

    def resolve(actual_program, value):
        assert actual_program is program
        assert value == "0x401000"
        return exact_address

    class FakeParser:
        AllowedDataTypes = SimpleNamespace(ALL="all")

        def __init__(self, *_args):
            pass

        def parse(self, value):
            assert value == "int"
            return data_type

    monkeypatch.setitem(sys.modules, "ghidra.util.data", SimpleNamespace(DataTypeParser=FakeParser))
    monkeypatch.setattr(AddressUtil, "resolve_address_or_symbol", resolve)
    monkeypatch.setattr(provider, "_resolve_address", lambda *_args, **_kw: pytest.fail("Data writes must not redirect to a thunk"))
    listing = SimpleNamespace(
        clearCodeUnits=lambda address, end, flag: seen.append(("clear", address, end, flag)),
        createData=lambda address, datatype: seen.append(("create", address, datatype)),
    )
    monkeypatch.setattr(provider, "_get_listing", lambda *_args, **_kw: listing)
    monkeypatch.setattr(provider, "_run_program_transaction", lambda _program, _label, fn: fn())
    await provider._handle_apply(
        {"addressorsymbol": "0x401000", "datatype": "int", FORCE_APPLY_CONFLICT_ID_KEY: "approved-conflict"},
        program_info=SimpleNamespace(program=program),
    )
    assert seen == [("clear", exact_address, ("end", 3), False), ("create", exact_address, data_type)]
