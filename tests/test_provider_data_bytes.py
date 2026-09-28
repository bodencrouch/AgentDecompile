from __future__ import annotations

import json
import sys

from types import SimpleNamespace
from typing import Any

import pytest

from agentdecompile_cli.mcp_server.providers.data import DataToolProvider


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
    monkeypatch.setattr(provider, "_resolve_address", lambda *_args, **_context: "100000520")
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
