"""Structural contract for the three inline-argparse entry points that
``tests/test_cli_contract.py`` does not cover: ``agentdecompile-server``
(``server.py:main``), ``agentdecompile-proxy`` (``server.py:proxy_main``) and
``agentdecompile-mcp`` / ``mcp-agentdecompile`` (``__main__.py:main``).

Each of these built its ``argparse.ArgumentParser`` inline inside the entry
function, so nothing could inspect the parser without running the entry
point (which starts PyGhidra, binds a port, or both). Task 4 extracted a
module-level, side-effect-free ``build_parser()`` (``build_proxy_parser()``
for the proxy) that the entry function now calls; this file exercises those
builders exactly the way ``test_cli_contract.py`` exercises the
``agentdecompile-recover`` / ``agentdecompile-corpus`` / etc. builders.

Parse-only: no test here calls ``main()``, ``proxy_main()``, or starts a
server or opens a port. Byte-for-byte identity of the extracted parsers
against the pre-refactor inline versions was proven out-of-band by
intercepting ``argparse.ArgumentParser.parse_args`` at base commit 1cdc0f9
and diffing ``format_help()`` plus every action's (option_strings, dest,
default, type, choices, nargs, required, const) against the builders'
output; see the Task 4 commit message for the exact procedure.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
from typing import Any

import pytest

from tests.test_cli_contract import (
    _function_table,
    _module_source,
    _NamespaceReads,
    _resolve_delegated_reads,
    dests_of,
)

pytestmark = pytest.mark.unit

# (prog, module_name, builder_name, entry_func_name)
SERVER_CLIS: tuple[tuple[str, str, str, str], ...] = (
    ("agentdecompile-server", "agentdecompile_cli.server", "build_parser", "main"),
    ("agentdecompile-proxy", "agentdecompile_cli.server", "build_proxy_parser", "proxy_main"),
    ("mcp-agentdecompile", "agentdecompile_cli.__main__", "build_parser", "main"),
)


def _build(module_name: str, builder_name: str) -> argparse.ArgumentParser:
    module = importlib.import_module(module_name)
    builder = getattr(module, builder_name)
    return builder()


def _reads_of_args(func: Any) -> tuple[set[str], bool, set[tuple[str, int | str]]]:
    """Attribute reads of the literal local/parameter name ``args`` in ``func``.

    Unlike ``test_cli_contract._handler_reads`` (which assumes the namespace is
    the function's *first* parameter -- true for ``main``/``proxy_main``, whose
    namespace is a local called ``args``, but false for a helper like
    ``_setup_project_paths(parser, args)`` where ``args`` is the *second*
    parameter), this always scans for the name ``args`` specifically, matching
    how every reader in server.py/__main__.py actually names it.
    """
    source = inspect.getsource(func)
    tree = ast.parse(source)
    function = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    reads = _NamespaceReads("args")
    for statement in function.body:
        reads.visit(statement)
    return reads.attrs, reads.passed_whole, reads.delegates


@pytest.mark.parametrize(
    ("prog", "module_name", "builder_name", "entry_func_name"),
    SERVER_CLIS,
    ids=[case[0] for case in SERVER_CLIS],
)
def test_help_renders_and_version_exits_zero(prog: str, module_name: str, builder_name: str, entry_func_name: str) -> None:
    """Help/usage must render without raising, and --version (if declared) exits 0."""
    parser = _build(module_name, builder_name)
    parser.format_help()
    parser.format_usage()

    has_version = any(isinstance(a, argparse._VersionAction) for a in parser._actions)
    if not has_version:
        pytest.skip(f"{prog}: declares no --version action")

    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args(["--version"])
    assert exit_info.value.code == 0


@pytest.mark.parametrize(
    ("prog", "module_name", "builder_name", "entry_func_name"),
    SERVER_CLIS,
    ids=[case[0] for case in SERVER_CLIS],
)
def test_unknown_flag_exits_2_without_traceback(prog: str, module_name: str, builder_name: str, entry_func_name: str) -> None:
    parser = _build(module_name, builder_name)
    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args(["--nonexistent-flag-zz"])
    assert exit_info.value.code == 2


@pytest.mark.parametrize(
    ("prog", "module_name", "builder_name", "entry_func_name"),
    SERVER_CLIS,
    ids=[case[0] for case in SERVER_CLIS],
)
def test_no_option_string_declared_twice(prog: str, module_name: str, builder_name: str, entry_func_name: str) -> None:
    parser = _build(module_name, builder_name)
    flags: dict[str, int] = {}
    for action in parser._actions:
        for flag in action.option_strings:
            flags[flag] = flags.get(flag, 0) + 1
    duplicates = {flag: count for flag, count in flags.items() if count > 1}
    assert not duplicates, f"{prog}: duplicate option declarations: {duplicates}"


def _shared_dest_groups(parser: argparse.ArgumentParser) -> dict[str, list[argparse.Action]]:
    groups: dict[str, list[argparse.Action]] = {}
    for action in parser._actions:
        if not action.dest or action.dest in (argparse.SUPPRESS, "help"):
            continue
        groups.setdefault(action.dest, []).append(action)
    return {dest: actions for dest, actions in groups.items() if len(actions) > 1}


@pytest.mark.parametrize(
    ("prog", "module_name", "builder_name", "entry_func_name"),
    SERVER_CLIS,
    ids=[case[0] for case in SERVER_CLIS],
)
def test_shared_dests_are_only_valid_onoff_pairs(prog: str, module_name: str, builder_name: str, entry_func_name: str) -> None:
    """A dest shared by two actions is only legitimate as a store_true/store_false pair.

    For each such pair, validate the actual semantics rather than trusting the
    action classes alone: the "on" flag must set True, the "off" flag must set
    False, and whichever is given last on the command line must win (that is
    how argparse resolves two actions sharing one dest).
    """
    parser = _build(module_name, builder_name)
    groups = _shared_dest_groups(parser)
    problems: list[str] = []

    for dest, actions in groups.items():
        if len(actions) != 2:
            problems.append(f"{prog}: dest {dest!r} shared by {len(actions)} actions (expected an on/off pair of 2)")
            continue
        by_class = {type(a).__name__: a for a in actions}
        if set(by_class) != {"_StoreTrueAction", "_StoreFalseAction"}:
            problems.append(f"{prog}: dest {dest!r} shared by non on/off actions: {[type(a).__name__ for a in actions]}")
            continue
        on_action = by_class["_StoreTrueAction"]
        off_action = by_class["_StoreFalseAction"]
        on_flag = on_action.option_strings[0]
        off_flag = off_action.option_strings[0]

        negations = {f"--no-{flag[2:]}" for flag in on_action.option_strings if flag.startswith("--")}
        if off_flag not in negations:
            problems.append(f"{prog}: off flag {off_flag!r} is not the negation of on flag(s) {on_action.option_strings!r}")
            continue

        ns_on = parser.parse_args([on_flag])
        if getattr(ns_on, dest) is not True:
            problems.append(f"{prog}: {on_flag} did not set {dest}=True")

        ns_off = parser.parse_args([off_flag])
        if getattr(ns_off, dest) is not False:
            problems.append(f"{prog}: {off_flag} did not set {dest}=False")

        ns_on_then_off = parser.parse_args([on_flag, off_flag])
        if getattr(ns_on_then_off, dest) is not False:
            problems.append(f"{prog}: {on_flag} then {off_flag} did not leave {dest}=False (last-one-wins)")

        ns_off_then_on = parser.parse_args([off_flag, on_flag])
        if getattr(ns_off_then_on, dest) is not True:
            problems.append(f"{prog}: {off_flag} then {on_flag} did not leave {dest}=True (last-one-wins)")

    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    ("prog", "module_name", "builder_name", "entry_func_name"),
    SERVER_CLIS,
    ids=[case[0] for case in SERVER_CLIS],
)
def test_everything_is_optional(prog: str, module_name: str, builder_name: str, entry_func_name: str) -> None:
    """Project rule: every CLI arg needs a sane default, never required.

    No action may be declared ``required=True`` and no positional may demand a
    value (``nargs`` other than ``"*"``/``"?"`` on a positional with no option
    strings is a mandatory positional). ``parse_args([])`` must succeed for all
    three commands.
    """
    parser = _build(module_name, builder_name)
    problems: list[str] = []
    for action in parser._actions:
        if action.required:
            problems.append(f"{prog}: {action.option_strings or action.dest} is required=True")
        if not action.option_strings and action.nargs not in ("*", "?"):
            problems.append(f"{prog}: positional {action.dest!r} has nargs={action.nargs!r} (mandatory positional)")
    assert not problems, "\n".join(problems)

    # Must not raise or exit non-zero.
    namespace = parser.parse_args([])
    assert isinstance(namespace, argparse.Namespace)


# --------------------------------------------------------------------------- #
# dest reads vs declared dests
# --------------------------------------------------------------------------- #

# Helper functions in the same module that receive the parsed ``args``
# namespace and read attributes off it. ``main``/``proxy_main`` pass ``args``
# to each of these by name at their call sites, so the delegate walk in
# ``_resolve_delegated_reads`` already reaches all of them; they are also
# listed here and scanned directly so a chain the delegate walk's depth cap
# or call-site shape misses is not silently skipped.
EXTRA_READERS: dict[str, tuple[str, ...]] = {
    "agentdecompile-server": ("_set_env_from_args", "_setup_project_paths"),
    "agentdecompile-proxy": (),
    "mcp-agentdecompile": ("_handle_connect_mode", "_initialize_pygidra_blocking"),
}


def _dict_literal_string_keys(func: Any, var_name: str) -> set[str] | None:
    """String keys of a top-level ``<var_name> = {...}`` dict literal in ``func``.

    ``_set_env_from_args`` reads ``getattr(args, arg_name, None)`` where
    ``arg_name`` is the loop variable of ``for arg_name, env_name in
    mappings.items()``. That is a computed attribute name -- ``_NamespaceReads``
    cannot resolve it and marks the read ``passed_whole`` instead of recording
    an attribute, which would otherwise let real reads hide behind a read that
    "looked" checked. The dict literal's own keys give the resolved attribute
    names; ``None`` means no such literal was found (the read stays unresolved
    and must be surfaced, not silently dropped).
    """
    source = inspect.getsource(func)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == var_name
            and isinstance(node.value, ast.Dict)
        ):
            keys: set[str] = set()
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
                else:
                    return None
            return keys
    return None


@pytest.mark.parametrize(
    ("prog", "module_name", "builder_name", "entry_func_name"),
    SERVER_CLIS,
    ids=[case[0] for case in SERVER_CLIS],
)
def test_entry_point_only_reads_declared_dests(prog: str, module_name: str, builder_name: str, entry_func_name: str) -> None:
    """Reading ``args.X`` (or ``getattr(args, "X", ...)``) for an undeclared dest
    is ``AttributeError`` the first time that line runs. These are flat
    parsers (no subcommands), so every dest the entry function or its direct
    helpers read is checked against the single declared dest set.
    """
    parser = _build(module_name, builder_name)
    declared = dests_of(parser)

    module = importlib.import_module(module_name)
    entry_func = getattr(module, entry_func_name)
    attrs, entry_passed_whole, delegates = _reads_of_args(entry_func)
    unresolved = 1 if entry_passed_whole else 0

    source = _module_source(module_name)
    table = _function_table((source,))

    # Delegates found by walking calls that pass ``args`` on whole from the
    # entry function (e.g. ``_setup_project_paths(parser, args)``).
    attrs = set(attrs) | _resolve_delegated_reads(delegates, table)

    # Helper functions known (by direct inspection) to receive ``args`` even
    # when the call site does not literally pass the identifier `args` at the
    # entry-function call site AST depth this check follows (e.g. functions
    # invoked from inside a nested helper). Scanned directly so a chain the
    # delegate walk misses is not silently skipped.
    for helper_name in EXTRA_READERS[prog]:
        helper = getattr(module, helper_name, None)
        assert helper is not None, f"{prog}: expected helper {helper_name} in {module_name}"
        helper_attrs, helper_passed_whole, helper_delegates = _reads_of_args(helper)
        attrs |= helper_attrs
        attrs |= _resolve_delegated_reads(helper_delegates, table)
        if helper_passed_whole:
            # `_set_env_from_args` reads `getattr(args, arg_name, None)` where
            # `arg_name` is a loop variable bound from `mappings.items()` --
            # a computed attribute name `_NamespaceReads` cannot resolve on
            # its own. The dict literal's own keys give the real names.
            resolved = _dict_literal_string_keys(helper, "mappings")
            if resolved is not None:
                attrs |= resolved
            else:
                unresolved += 1

    undeclared = attrs - declared
    assert not undeclared, f"{prog}: reads undeclared dest(s) {sorted(undeclared)} (declared: {sorted(declared)})"

    # Not a correctness assertion, just a visible count so a green result here
    # is not mistaken for "every possible read path was scanned": any read
    # this static walk could not resolve to a concrete attribute name is
    # reported, not silently folded into "checked".
    print(
        f"{prog}: checked {len(attrs)} distinct dest read(s), "
        f"{unresolved} unresolved computed read site(s): {sorted(attrs)}",
    )


# --------------------------------------------------------------------------- #
# help-rendered default vs actual parsed default (Task 6 / D1, D2)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("prog", "module_name", "builder_name", "entry_func_name"),
    SERVER_CLIS,
    ids=[case[0] for case in SERVER_CLIS],
)
def test_onoff_pair_default_matches_parsed_default(
    prog: str, module_name: str, builder_name: str, entry_func_name: str,
) -> None:
    """``ArgumentDefaultsHelpFormatter`` prints ``action.default`` verbatim.

    For a dest shared by a ``store_true``/``store_false`` on/off pair, argparse
    resolves ``parse_args([])`` by walking the actions in declaration order and
    keeping the *first* action's default that applies -- so whichever action
    was declared first silently wins the real parsed default, while the
    formatter still prints each action's own (possibly different, often
    implicit) ``.default`` next to its own flag. D1/D2 were exactly this: the
    ``store_false`` action had no explicit ``default=`` kwarg, so argparse gave
    it an implicit ``True``, and the help text for ``--no-require-auth`` /
    ``--no-enable-exchange`` printed "(default: True)" while
    ``parse_args([])`` actually produced ``None``.

    This check is structural, not textual: it does not scan rendered help
    strings (which can legitimately explain the default in prose, e.g. "Default:
    %(default)s (follows AGENT_DECOMPILE_AUTH_ENABLED, else off)"). It instead
    compares each action's own ``.default`` attribute -- the exact value
    ``ArgumentDefaultsHelpFormatter`` substitutes for ``%(default)s`` -- against
    the real ``parse_args([]).<dest>`` value. Any future on/off pair that omits
    ``default=`` on one side (or a ``set_defaults`` call that only reaches one
    of the two actions) will fail here.
    """
    parser = _build(module_name, builder_name)
    groups = _shared_dest_groups(parser)
    real_defaults = vars(parser.parse_args([]))

    problems: list[str] = []
    for dest, actions in groups.items():
        by_class = {type(a).__name__: a for a in actions}
        if set(by_class) != {"_StoreTrueAction", "_StoreFalseAction"}:
            # Not an on/off pair; covered by test_shared_dests_are_only_valid_onoff_pairs.
            continue
        if dest not in real_defaults:
            problems.append(f"{prog}: dest {dest!r} not present in parse_args([]) namespace")
            continue
        real_default = real_defaults[dest]
        for action in actions:
            if action.default != real_default:
                problems.append(
                    f"{prog}: {action.option_strings[0]} help would render "
                    f"'(default: {action.default!r})' but parse_args([]).{dest} is {real_default!r}",
                )

    assert not problems, "\n".join(problems)
