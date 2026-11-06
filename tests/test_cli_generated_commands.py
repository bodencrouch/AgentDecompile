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


def test_propagate_named_int_params_are_not_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: `propagateMaxInstructions`/`propagateMaxCandidates` are
    genuine integers (mcp_server/tool_providers.py `_INT_FRAGMENTS`) but also
    start with the `propagate` boolean-prefix pattern. Checking the bool
    fragments/prefixes before the int fragments (as a first version of this
    fix did) misclassifies them as bool; the array param
    `propagateProgramPaths` also starts with `propagate` and additionally
    contains "path", so it must land on `str`, not click.Path or bool."""
    cmd = cli_module.main.commands["manage-function"]
    by_name = {p.name: p for p in cmd.params}
    assert isinstance(by_name["propagate_max_instructions"].type, cli_module._HexAwareIntParamType)
    assert isinstance(by_name["propagate_max_candidates"].type, cli_module._HexAwareIntParamType)
    assert isinstance(by_name["propagate_program_paths"].type, click.types.StringParamType)
    assert not isinstance(by_name["propagate_program_paths"].type, click.Path)
    # `propagate` itself (no suffix) is the genuine boolean flag.
    assert isinstance(by_name["propagate"].type, click.types.BoolParamType)


def test_manage_strings_value_is_string_not_int(monkeypatch: pytest.MonkeyPatch) -> None:
    """`value` is ambiguous by name alone: search-constants/manage-enums use
    it as a number, but manage-strings uses it as the literal text being
    written (strings.py:89 declares it a string explicitly; strings.py:558
    `_require_str`). The generic "value" fragment (used for the numeric
    tools) must not win here -- covered by `_CLI_OPTION_TYPE_OVERRIDES`."""
    cmd = cli_module.main.commands["manage-strings"]
    param = next(p for p in cmd.params if p.name == "value")
    assert isinstance(param.type, click.types.StringParamType)

    result, seen = _invoke(monkeypatch, ["manage-strings", "--mode", "create", "--value", "hello world"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert seen["payload"].get("value") == "hello world"


def test_search_constants_value_stays_int(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check for the other side of the same ambiguous name: search-constants'
    `value` genuinely is numeric (constants.py:118 `_get_int`) and must be
    unaffected by the manage-strings override."""
    cmd = cli_module.main.commands["search-constants"]
    param = next(p for p in cmd.params if p.name == "value")
    assert isinstance(param.type, cli_module._HexAwareIntParamType)


# _CLI_OPTION_TYPE_OVERRIDES entries are per-(tool, param) evidence-backed
# exceptions. "maxFiles" is a second, narrower kind of exception: it isn't
# overridden per-tool, it's added directly to `_CLI_INT_FRAGMENTS` (see that
# table's docstring) because export-context's own inputSchema declares it an
# integer (context_substrate.py:85), stronger evidence than the server's
# generic name-based fallback ("string", since "maxfiles" isn't literally in
# the server's own _INT_FRAGMENTS list).
_SCHEMA_FALLBACK_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset(cli_module._CLI_OPTION_TYPE_OVERRIDES) | frozenset(
    {(cli_module.Tool.EXPORT_CONTEXT.value, "maxFiles")},
)


def test_generated_option_types_match_server_schema_fallback() -> None:
    """Parity check (R3): for every generated command's param, the CLI's
    inferred type must agree with the type the MCP server itself would fall
    back to for the same param name (mcp_server/tool_providers.py
    `_infer_param_schema`, the function `_generated_option_type` was built
    to mirror). This is the "evidence" R3 asked for, and it is meant to
    catch future drift if either copy of the fragment tables changes without
    the other.

    Two documented exceptions:
      - array params: the server calls these "array", the CLI has no bare
        multi-value option syntax for a generated flat command, so they stay
        `str` (comma-separated) -- see `_CLI_ARRAY_PARAMS`.
      - integer params: the CLI additionally accepts 0x/0o/0b-prefixed
        literals via `_HexAwareIntParamType`, still fundamentally "integer".
      - anything listed in `_CLI_OPTION_TYPE_OVERRIDES` (tool, param) pairs,
        where a provider's own declared inputSchema is stronger evidence
        than the server's generic name-based fallback (see that table's
        docstring for the citations).
    """
    from agentdecompile_cli.mcp_server import tool_providers as tp

    mismatches: list[str] = []
    for tool_name in cli_module.TOOLS:
        for param in cli_module._supported_cli_tool_params(tool_name):
            if (tool_name, param) in _SCHEMA_FALLBACK_EXCEPTIONS:
                continue
            ours = cli_module._generated_option_type(tool_name, param)
            server_type = tp._infer_param_schema(param)["type"]
            if server_type == "array":
                server_type = "string"  # our documented array->str exception
            if isinstance(ours, click.Path):
                continue  # path substring guess isn't part of the server's fallback vocabulary
            if ours is bool:
                ours_label = "boolean"
            elif ours is cli_module._CLI_HEX_INT:
                ours_label = "integer"
            elif ours is str:
                ours_label = "string"
            else:
                ours_label = repr(ours)
            if ours_label != server_type:
                mismatches.append(f"{tool_name}.{param}: cli={ours_label} server_fallback={server_type}")

    assert not mismatches, "CLI/server type-inference drift:\n" + "\n".join(mismatches)


# --------------------------------------------------------------------------- #
# _call_raw's inspect-memory format/mode alias guard
# --------------------------------------------------------------------------- #


def test_memory_run_explicit_mode_still_gets_format_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The format-injection guard must only skip the default when the alias
    target (`mode`) is actually absent -- an explicit `--mode read` must
    still get the usual `format=markdown` rendering default, unaffected by
    the inspect-memory alias quirk."""
    result, seen = _invoke(monkeypatch, ["memory", "run", "--mode", "read", "--address", "0x100"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert seen["payload"].get("mode") == "read"
    assert seen["payload"].get("format") == "markdown"


def test_memory_run_omitted_mode_sends_no_format_either(monkeypatch: pytest.MonkeyPatch) -> None:
    """Omitting --mode must not leak the CLI's own format=markdown rendering
    default into the backend's `mode` slot via the format->mode alias
    (TOOLS_LIST.md documents `read-memory(..., format)` as a mode synonym)."""
    result, seen = _invoke(monkeypatch, ["memory", "run"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert "mode" not in seen["payload"]


def test_generated_inspect_memory_command_gets_the_same_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard is keyed on the *resolved* canonical tool name, so the
    generated flat `inspect-memory` command (a separate click.Command from
    `memory run`, registered because Tool.INSPECT_MEMORY isn't in
    `_TOOLS_WITH_CURATED_COMMANDS`'s naming) is covered too, not just the
    hand-written `memory run` spelling. `read-memory` is a server-side-only
    alias (NON_ADVERTISED_TOOL_ALIASES) with no corresponding CLI command in
    this build, so it isn't exercised here directly."""
    result, seen = _invoke(monkeypatch, ["inspect-memory"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert "mode" not in seen["payload"]
    assert "format" not in seen["payload"]


# --------------------------------------------------------------------------- #
# Additional F10 fixes found during review: function-tags, get-references
# --------------------------------------------------------------------------- #


def test_function_tags_run_no_longer_requires_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend default: mode="list" (getfunction.py `_handle_tags`)."""
    result, seen = _invoke(monkeypatch, ["function-tags", "run"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert "mode" not in seen["payload"]


def test_references_run_no_longer_requires_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Omitting --target routes to a whole-program index
    (mcp_server/providers/xrefs.py `_handle_index`), so it must not be
    force-required."""
    result, seen = _invoke(monkeypatch, ["references", "run"])
    assert result.exit_code == 0, f"{result.exception!r} {result.output}"
    assert "target" not in seen["payload"]
