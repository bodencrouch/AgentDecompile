"""Focused tests for call-scoped context in ``ToolProvider`` helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agentdecompile_cli.mcp_server.tool_providers import ActionableError, ToolProvider
from agentdecompile_cli.mcp_utils.address_util import AddressUtil


class _NestedDispatchProvider(ToolProvider):
    async def _scoped_action(self, _args: dict, *, program_info=None):
        return program_info

    async def _legacy_action(self, _args: dict):
        return "legacy"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_nested_dispatch_forwards_explicit_program_info() -> None:
    provider = _NestedDispatchProvider()
    scoped_info = SimpleNamespace(program=object())

    result = await provider._dispatch_handler(
        {},
        "read",
        {"read": "_scoped_action"},
        program_info=scoped_info,
    )
    legacy_handler = provider._dispatch_handler(
        {"read": provider._scoped_action},
        "read",
        "action",
        program_info=None,
    )

    assert result is scoped_info
    assert await legacy_handler({}) is None
    assert await provider._dispatch_handler(
        {},
        "read",
        {"read": "_legacy_action"},
        program_info=scoped_info,
    ) == "legacy"


@pytest.mark.unit
def test_require_program_distinguishes_omitted_context_from_explicit_none() -> None:
    provider = ToolProvider()
    provider.program_info = SimpleNamespace(program=object())

    provider._require_program()
    with pytest.raises(ActionableError, match="No program loaded"):
        provider._require_program(program_info=None)
    provider.program_info = None
    provider._require_program(program_info=SimpleNamespace(program=object()))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("helper_name", "program_method"),
    [
        ("_get_function_manager", "getFunctionManager"),
        ("_get_listing", "getListing"),
        ("_get_memory", "getMemory"),
        ("_get_symbol_table", "getSymbolTable"),
    ],
)
def test_program_accessors_use_call_scoped_context(
    helper_name: str,
    program_method: str,
) -> None:
    lifecycle_program = MagicMock()
    scoped_program = MagicMock()
    explicit_program = MagicMock()
    expected = object()
    explicit_expected = object()
    getattr(scoped_program, program_method).return_value = expected
    getattr(explicit_program, program_method).return_value = explicit_expected
    provider = ToolProvider()
    provider.program_info = SimpleNamespace(program=lifecycle_program)

    result = getattr(provider, helper_name)(
        program_info=SimpleNamespace(program=scoped_program),
    )

    assert result is expected
    assert getattr(provider, helper_name)(explicit_program, program_info=None) is explicit_expected
    with pytest.raises(ValueError, match="No program loaded"):
        getattr(provider, helper_name)(program_info=None)
    getattr(lifecycle_program, program_method).assert_not_called()


@pytest.mark.unit
def test_resolve_address_uses_explicit_context_and_program_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle_program = object()
    scoped_program = object()
    explicit_program = object()
    seen: list[object] = []
    provider = ToolProvider()
    provider.program_info = SimpleNamespace(program=lifecycle_program)
    monkeypatch.setattr(
        AddressUtil,
        "resolve_address_or_symbol_prefer_thunk",
        lambda program, _value: seen.append(program) or program,
    )

    assert provider._resolve_address(
        "target",
        program_info=SimpleNamespace(program=scoped_program),
    ) is scoped_program
    assert provider._resolve_address(
        "target",
        explicit_program,
        program_info=None,
    ) is explicit_program
    with pytest.raises(ValueError, match="program_info"):
        provider._resolve_address("target", program_info=None)

    assert seen == [scoped_program, explicit_program]


@pytest.mark.unit
def test_resolve_function_uses_call_scoped_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle_program = MagicMock()
    scoped_program = MagicMock()
    explicit_program = MagicMock()
    function = MagicMock()
    function.getName.return_value = "target"
    function.getEntryPoint.return_value = "00100000"
    function_manager = MagicMock()
    function_manager.getFunctions.return_value = [function]
    function_manager.getFunctionCount.return_value = 1
    scoped_program.getFunctionManager.return_value = function_manager
    explicit_program.getFunctionManager.return_value = function_manager
    provider = ToolProvider()
    provider.program_info = SimpleNamespace(program=lifecycle_program)
    monkeypatch.setattr(AddressUtil, "parse_address", lambda _program, _value: None)

    assert provider._resolve_function(
        "target",
        program_info=SimpleNamespace(program=scoped_program),
    ) is function
    assert provider._resolve_function(
        "target",
        explicit_program,
        program_info=None,
    ) is function
    lifecycle_program.getFunctionManager.assert_not_called()
    assert provider._resolve_function("target", program_info=None) is None
