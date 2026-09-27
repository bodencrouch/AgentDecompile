"""Regression tests for Task 9: generated-command construction and error exits.

Covers three defect classes found in ``agentdecompile_cli.cli`` (see
``_create_dynamic_commands`` and ``_call``):

F2  A tool whose own parameter is literally named ``tool`` (run-decomp-match,
    run-external-re-scan) crashed ``_call(ctx, tool, **kwargs)`` with
    "got multiple values for argument 'tool'" because the positional ``tool``
    collided with the ``tool=`` kwarg. The generated wrapper additionally
    swallowed the exception via its own try/except before ``_run_async`` ever
    saw it, so the process still exited 0.

F10 Generated commands force-required ``addressOrSymbol``/``action``/``mode``
    by a blanket name match regardless of whether the backend has a default
    (manage-strings mode=list, get-function's function/functionIdentifier
    aliases) -- now driven by an evidenced per-tool table.

P3  Generated option types were guessed from name substrings, so
    ``maxFiles`` (int) became a click.Path, ``overrideMaxFunctionsLimit``
    (bool) became an int rejecting "true", and hex-looking numeric values
    like ``0x20`` were rejected by plain click.INT.

All tests stub the network per repo policy (AGENTS.md: always stub the
network; no servers, ports, systemctl, recovery operations, kills) by
monkeypatching ``agentdecompile_cli.cli._execute_tool_call``, the same seam
``tests/test_cli_contract.py`` uses.
"""

from __future__ import annotations

from typing import Any

import click
import pytest

from agentdecompile_cli import cli as cli_module

pytestmark = pytest.mark.unit


def _success(text: str = "ok") -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _invoke(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> tuple[Any, dict[str, Any]]:
    """Invoke a generated command with the transport stubbed to succeed.

    Returns (click Result, captured payload dict).
    """
    from click.testing import CliRunner

    seen: dict[str, Any] = {}

    async def fake_execute(ctx: click.Context, tool: str, payload: dict[str, Any], client_override: Any = None) -> Any:
        seen["tool"] = tool
        seen["payload"] = dict(payload)
        return _success()

    monkeypatch.delenv("AGENTDECOMPILE_LOCAL_MODE", raising=False)
    monkeypatch.setattr(cli_module, "_execute_tool_call", fake_execute)
    result = CliRunner().invoke(cli_module.main, argv)
    return result, seen


# --------------------------------------------------------------------------- #
# F2: `tool` parameter collision with _call(ctx, tool, **kwargs)
# --------------------------------------------------------------------------- #


def test_run_decomp_match_sends_tool_param_and_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_call`'s positional `tool` must not collide with a tool param named `tool`."""
    result, seen = _invoke(monkeypatch, ["run-decomp-match", "--tool", "objdiff"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert seen["payload"].get("tool") == "objdiff"


def test_run_external_re_scan_sends_tool_param_and_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    result, seen = _invoke(
        monkeypatch,
        ["run-external-re-scan", "--binary-path", "/tmp/bin", "--tool", "yara"],
    )
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert seen["payload"].get("tool") == "yara"


def test_generated_command_forced_exception_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any exception raised before/at the transport must produce a non-zero exit.

    Before the fix, the generated wrapper's inner try/except caught and
    reported the error via handle_command_error() but swallowed it before
    `_run_async` could see it and sys.exit(1), so the process exited 0 on
    every such error -- including the F2 collision itself.
    """
    from click.testing import CliRunner

    async def boom(ctx: click.Context, tool: str, payload: dict[str, Any], client_override: Any = None) -> Any:
        raise RuntimeError("simulated transport failure")

    monkeypatch.delenv("AGENTDECOMPILE_LOCAL_MODE", raising=False)
    monkeypatch.setattr(cli_module, "_execute_tool_call", boom)
    result = CliRunner().invoke(cli_module.main, ["get-current-function"])
    assert result.exit_code != 0
    assert "simulated transport failure" in result.output


def test_generated_command_success_still_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check: the exit-code fix must not break the success path."""
    result, _seen = _invoke(monkeypatch, ["get-current-function"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"


# --------------------------------------------------------------------------- #
# F10: options that used to be force-required despite a backend default
# --------------------------------------------------------------------------- #

def test_manage_strings_runs_without_mode_and_sends_no_mode_key(monkeypatch: pytest.MonkeyPatch) -> None:
    result, seen = _invoke(monkeypatch, ["manage-strings"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert "mode" not in seen["payload"]


def test_get_function_runs_with_only_function_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """get-function accepts function/addressOrSymbol/functionIdentifier aliases;
    requiring addressOrSymbol specifically (the old blanket rule) broke this."""
    result, seen = _invoke(monkeypatch, ["get-function", "--function-identifier", "main"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert seen["payload"].get("functionIdentifier") == "main"
    assert "addressOrSymbol" not in seen["payload"]


@pytest.mark.parametrize(
    "argv",
    [
        ["symbols", "run"],
        ["memory", "run"],
        ["datatypes", "run"],
        ["structures", "run"],
        ["comments", "run"],
        ["bookmarks", "run"],
        ["constants", "run"],
        ["vtables", "run"],
    ],
    ids=["symbols", "memory", "datatypes", "structures", "comments", "bookmarks", "constants", "vtables"],
)
def test_hand_written_run_commands_no_longer_require_selector(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """These `<group> run` commands previously required --mode/--action even
    though their backend providers have a documented default (see the
    per-command citations next to each click.option in cli.py)."""
    result, seen = _invoke(monkeypatch, argv)
    assert result.exit_code == 0, f"{argv} -> {result.exception!r} {result.output}"
    assert "mode" not in seen["payload"]
    assert "action" not in seen["payload"]


def test_dataflow_no_longer_requires_direction(monkeypatch: pytest.MonkeyPatch) -> None:
    result, seen = _invoke(monkeypatch, ["dataflow", "--function-address", "0x1000"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert "direction" not in seen["payload"]
    assert seen["payload"].get("functionAddress") == "0x1000"


def test_dataflow_still_requires_function_address(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _seen = _invoke(monkeypatch, ["dataflow", "--direction", "forward"])
    assert result.exit_code != 0


def test_callgraph_run_no_longer_requires_function(monkeypatch: pytest.MonkeyPatch) -> None:
    result, seen = _invoke(monkeypatch, ["callgraph", "run"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert "functionIdentifier" not in seen["payload"]


@pytest.mark.parametrize(
    "argv",
    [["manage-function"], ["manage-files"]],
    ids=["manage-function", "manage-files"],
)
def test_genuinely_required_generated_commands_still_error_without_mode(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """manage-function / manage-files providers raise with no default and no
    alternate alias when `mode` is omitted (project.py:2792, getfunction.py:349)."""
    result, _seen = _invoke(monkeypatch, argv)
    assert result.exit_code != 0


def test_apply_data_type_still_requires_address_and_datatype(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _seen = _invoke(monkeypatch, ["apply-data-type"])
    assert result.exit_code != 0


def test_create_label_still_requires_address_and_label(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _seen = _invoke(monkeypatch, ["create-label"])
    assert result.exit_code != 0


def test_get_data_still_requires_address_or_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _seen = _invoke(monkeypatch, ["get-data"])
    assert result.exit_code != 0


# --------------------------------------------------------------------------- #
# P3: option type derivation (bool/int/path) from evidenced fragment tables
# --------------------------------------------------------------------------- #


def test_search_constants_accepts_hex_max_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repro: `search-constants --max-value 0x20` was rejected by plain
    click.INT before it ever reached the backend."""
    result, seen = _invoke(monkeypatch, ["search-constants", "--max-value", "0x20", "--min-value", "0x10"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert seen["payload"].get("maxValue") == 32
    assert seen["payload"].get("minValue") == 16


def test_override_max_functions_limit_accepts_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repro: `--override-max-functions-limit true` was rejected because the
    name-substring guess classified it as int (contains "max")."""
    result, seen = _invoke(monkeypatch, ["search-code", "--override-max-functions-limit", "true", "--pattern", "x"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert seen["payload"].get("overrideMaxFunctionsLimit") is True


def test_strip_leading_path_is_not_a_path_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repro: `stripLeadingPath` is a boolean but the old rule matched "path"
    in the name and forced click.Path."""
    cmd = cli_module.main.commands["manage-files"]
    param = next(p for p in cmd.params if p.name == "strip_leading_path")
    assert isinstance(param.type, click.types.BoolParamType)


def test_max_files_is_int_not_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repro: `maxFiles` (export-context) is an integer count but the old
    rule matched "file" in the name and forced click.Path."""
    cmd = cli_module.main.commands["export-context"]
    param = next(p for p in cmd.params if p.name == "max_files")
    assert not isinstance(param.type, click.Path)
    assert isinstance(param.type, cli_module._HexAwareIntParamType)
