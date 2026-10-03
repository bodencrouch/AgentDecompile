"""Structural contract for every CLI surface: parsers, options and handler wiring.

Three defect classes motivate this file, all found by introspection rather than
by running commands:

* A click option may set an explicit parameter name that the callback does not
  accept (``@click.option("--keep-checked-out", "keepCheckedOut")`` against a
  callback taking ``keep_checked_out``). Click splats the parameters into the
  callback, so such a command raises ``TypeError`` on every invocation and can
  never run. Eight commands were broken this way.
* Declaring one option twice on a command lets one declaration silently win,
  so a flag the help advertises has no effect.
* An argparse handler may read ``args.X`` for a dest its subparser never
  declares, which is ``AttributeError`` at dispatch.

Everything here builds parser objects and inspects them. No command body runs,
no process starts, no port is opened and nothing is written, so the checks are
safe under the recovery-operation constraints in AGENTS.md.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import tomllib
from pathlib import Path
from typing import Any, Iterator

import click
import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]

# Argparse CLIs that expose a module-level ``build_parser()``.
ARGPARSE_CLIS: tuple[tuple[str, str], ...] = (
    ("agentdecompile-recover", "agentdecompile_recovery.cli"),
    ("agentdecompile-corpus", "agentdecompile_recovery.corpus.cli"),
    ("agentdecompile-reconstruct", "agentdecompile_recovery.frontdoor"),
    ("adgrid", "agentdecompile_grid.cli"),
)

# Modules that dispatch corpus subcommands. ``corpus/cli.py`` delegates part of
# its verb set to these, each with its own ``if cmd == "..."`` chain.
CORPUS_DISPATCH_MODULES: tuple[str, ...] = (
    "src/agentdecompile_recovery/corpus/cli.py",
    "src/agentdecompile_recovery/corpus/kx_cli.py",
    "src/agentdecompile_recovery/corpus/mizuchi_tools_cli.py",
)

# Attribute names used as the subcommand selector across these CLIs.
SELECTOR_ATTRS: frozenset[str] = frozenset({"cmd", "command", "subcommand", "verb", "action"})


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def subparser_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def dests_of(parser: argparse.ArgumentParser) -> set[str]:
    """Every attribute a namespace parsed by ``parser`` will carry."""
    dests: set[str] = set()
    for action in parser._actions:
        if action.dest and action.dest != "help" and action.dest != argparse.SUPPRESS:
            dests.add(action.dest)
    dests.update(parser._defaults)
    return dests


def walk_argparse(parser: argparse.ArgumentParser, prefix: str) -> Iterator[tuple[str, argparse.ArgumentParser]]:
    yield prefix, parser
    action = subparser_action(parser)
    if action is None:
        return
    seen: set[int] = set()
    for name, sub in action.choices.items():
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        yield from walk_argparse(sub, f"{prefix} {name}")


def walk_click(command: click.Command, prefix: str) -> Iterator[tuple[str, click.Command]]:
    yield prefix, command
    if isinstance(command, click.Group):
        for name, sub in command.commands.items():
            yield from walk_click(sub, f"{prefix} {name}")


def click_root() -> click.Group:
    from agentdecompile_cli.cli import main as root

    return root


def callback_signature(callback: Any) -> tuple[set[str], set[str], bool] | None:
    """(accepted, required, accepts_kwargs) for a click callback.

    ``@click.pass_context`` wraps the callback and supplies the leading context
    argument itself; ``inspect.signature`` unwraps to the original function, so
    that first parameter is dropped here.
    """
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return None
    params = list(signature.parameters.values())
    if hasattr(callback, "__wrapped__") and params and params[0].kind is params[0].POSITIONAL_OR_KEYWORD:
        params = params[1:]
    accepts_kwargs = any(p.kind is p.VAR_KEYWORD for p in params)
    named = {p.name for p in params if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}
    required = {
        p.name
        for p in params
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) and p.default is inspect.Parameter.empty
    }
    return named, required, accepts_kwargs


# --------------------------------------------------------------------------- #
# entry points
# --------------------------------------------------------------------------- #
def test_every_console_script_target_resolves() -> None:
    """Each ``[project.scripts]`` target must import and be callable."""
    scripts = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts, "no console scripts declared"
    broken: list[str] = []
    for name, target in sorted(scripts.items()):
        module_name, _, attribute = target.partition(":")
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            broken.append(f"{name} -> {target}: import failed: {type(exc).__name__}: {exc}")
            continue
        if not callable(getattr(module, attribute, None)):
            broken.append(f"{name} -> {target}: {attribute} missing or not callable")
    assert not broken, "console scripts do not resolve:\n" + "\n".join(broken)


# --------------------------------------------------------------------------- #
# click: binding contract
# --------------------------------------------------------------------------- #
def test_click_commands_bind_to_their_callbacks() -> None:
    """Click splats exposed parameters into the callback; names must line up.

    A mismatch is not a style problem. The command raises ``TypeError`` before
    its body runs, so it can never be invoked at all.
    """
    problems: list[str] = []
    for path, command in walk_click(click_root(), "agentdecompile"):
        # Groups are checked too: root `main` exposes 18 options of its own, and a
        # mismatch on a group callback fails exactly like a leaf command's.
        if command.callback is None:
            continue
        passed = {param.name for param in command.params if param.expose_value}
        # Argparse bridge leaves bypass Click parsing and populate ``args`` in
        # _ForwardAllCommand.parse_args. It is a real callback input even
        # though exposing it as a Click argument would consume forwarded flags.
        if getattr(command, "BRIDGED", False):
            passed.add("args")
        signature = callback_signature(command.callback)
        if signature is None:
            continue
        accepted, required, accepts_kwargs = signature
        if not accepts_kwargs:
            unexpected = passed - accepted
            if unexpected:
                problems.append(f"{path}: click passes {sorted(unexpected)}, callback accepts no such parameter")
        unfilled = required - passed
        if unfilled:
            problems.append(f"{path}: callback requires {sorted(unfilled)}, no exposed option supplies it")
    assert not problems, "click commands cannot bind their callbacks:\n" + "\n".join(problems)


def test_click_commands_declare_each_option_once() -> None:
    """A repeated option or parameter name lets one declaration silently win."""
    problems: list[str] = []
    for path, command in walk_click(click_root(), "agentdecompile"):
        names: dict[str, int] = {}
        flags: dict[str, int] = {}
        for param in command.params:
            names[param.name] = names.get(param.name, 0) + 1
            for flag in list(param.opts) + list(param.secondary_opts):
                flags[flag] = flags.get(flag, 0) + 1
        for name, count in names.items():
            if count > 1:
                problems.append(f"{path}: parameter name {name!r} declared {count} times")
        for flag, count in flags.items():
            if count > 1:
                problems.append(f"{path}: option {flag} declared {count} times")
    assert not problems, "duplicate CLI option declarations:\n" + "\n".join(problems)


def test_click_help_renders_for_every_command() -> None:
    problems: list[str] = []
    for path, command in walk_click(click_root(), "agentdecompile"):
        try:
            command.get_help(click.Context(command, info_name=path.split()[-1]))
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            problems.append(f"{path}: {type(exc).__name__}: {exc}")
    assert not problems, "click help failed to render:\n" + "\n".join(problems)


# --------------------------------------------------------------------------- #
# argparse: help, usage and parse behaviour
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("prog", "module_name"), ARGPARSE_CLIS, ids=[p for p, _ in ARGPARSE_CLIS])
def test_argparse_help_and_parse_never_traceback(prog: str, module_name: str) -> None:
    """Help must render, and a bad command line must exit 2 rather than raise.

    Only parsing happens here. Handlers are never dispatched.
    """
    root = importlib.import_module(module_name).build_parser()
    problems: list[str] = []
    for path, parser in walk_argparse(root, prog):
        argv = path.split()[1:]
        for label, renderer in (("help", parser.format_help), ("usage", parser.format_usage)):
            try:
                renderer()
            except Exception as exc:  # noqa: BLE001 - report, do not mask
                problems.append(f"{path}: {label} raised {type(exc).__name__}: {exc}")
        for label, extra in (("no arguments", []), ("unknown flag", ["--nonexistent-flag-zz"])):
            try:
                root.parse_args(argv + extra)
            except SystemExit as exit_signal:
                if exit_signal.code not in (0, 2):
                    problems.append(f"{path}: {label} exited {exit_signal.code}, expected 0 or 2")
            except Exception as exc:  # noqa: BLE001 - report, do not mask
                problems.append(f"{path}: {label} raised {type(exc).__name__}: {exc}")
    assert not problems, f"{prog} parser defects:\n" + "\n".join(problems)


def test_argparse_options_are_not_declared_twice() -> None:
    problems: list[str] = []
    for prog, module_name in ARGPARSE_CLIS:
        root = importlib.import_module(module_name).build_parser()
        for path, parser in walk_argparse(root, prog):
            flags: dict[str, int] = {}
            for action in parser._actions:
                for flag in action.option_strings:
                    flags[flag] = flags.get(flag, 0) + 1
            for flag, count in flags.items():
                if count > 1:
                    problems.append(f"{path}: option {flag} declared {count} times")
    assert not problems, "duplicate argparse option declarations:\n" + "\n".join(problems)


# --------------------------------------------------------------------------- #
# argparse: handler reads vs declared dests
# --------------------------------------------------------------------------- #
class _NamespaceReads(ast.NodeVisitor):
    """Collect ``<var>.attr`` reads, and note when ``<var>`` is passed on whole."""

    def __init__(self, var: str) -> None:
        self.var = var
        self.attrs: set[str] = set()
        self.passed_whole = False
        self.delegates: set[tuple[str, int | str]] = set()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id == self.var:
            self.attrs.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name: str | None = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        # `getattr(args, "unity_editor", None)` is a read of `unity_editor`, but it
        # is a Call node, so visit_Attribute never sees it. Harvesting the literal
        # name is what keeps these out of the "passed whole" bucket, where they
        # were counted as fully checked while being invisible.
        if (
            name == "getattr"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == self.var
            and len(node.args) >= 2
        ):
            attribute = node.args[1]
            if isinstance(attribute, ast.Constant) and isinstance(attribute.value, str):
                self.attrs.add(attribute.value)
            else:
                # A computed attribute name cannot be resolved statically.
                self.passed_whole = True
            self.generic_visit(node)
            return
        # `vars(args)` and `**vars(args)` hand over every field at once.
        if name == "vars" and any(
            isinstance(argument, ast.Name) and argument.id == self.var for argument in node.args
        ):
            self.passed_whole = True
        for position, argument in enumerate(node.args):
            if isinstance(argument, ast.Name) and argument.id == self.var:
                self.passed_whole = True
                # `return run_inspect(args)` -- the reads are in run_inspect.
                # The position matters: `_run_loop(loop, args)` passes it second.
                if name is not None:
                    self.delegates.add((name, position))
        for keyword in node.keywords:
            if isinstance(keyword.value, ast.Name) and keyword.value.id == self.var:
                self.passed_whole = True
                if name is not None and keyword.arg is not None:
                    self.delegates.add((name, keyword.arg))
        self.generic_visit(node)


def _selected_commands(test: ast.expr, var: str, attr: str, alias: str | None) -> set[str]:
    """Subcommand names a test such as ``args.cmd == "x"`` or ``cmd == "x"`` selects."""
    selected: set[str] = set()
    for node in ast.walk(test):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        matches_attr = (
            isinstance(left, ast.Attribute)
            and isinstance(left.value, ast.Name)
            and left.value.id == var
            and left.attr == attr
        )
        matches_alias = alias is not None and isinstance(left, ast.Name) and left.id == alias
        if not (matches_attr or matches_alias):
            continue
        for operator, comparator in zip(node.ops, node.comparators):
            if isinstance(operator, ast.Eq) and isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                selected.add(comparator.value)
            elif isinstance(operator, ast.In) and isinstance(comparator, (ast.Set, ast.Tuple, ast.List)):
                selected.update(
                    element.value
                    for element in comparator.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                )
    return selected


def _scan_dispatch(source: Path) -> dict[str, tuple[set[str], bool, set[str]]]:
    """Map subcommand -> (attributes read, namespace passed on whole, delegate names)."""
    found: dict[str, tuple[set[str], bool, set[str]]] = {}
    tree = ast.parse(source.read_text())
    for function in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        candidates = {a.arg for a in function.args.args}
        candidates |= {
            target.id
            for node in ast.walk(function)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        # ``cmd = args.cmd`` makes bare ``cmd`` a selector for namespace ``args``.
        aliases: dict[str, tuple[str, str]] = {}
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.attr in SELECTOR_ATTRS
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = (node.value.value.id, node.value.attr)

        def record(command: str, reads: _NamespaceReads) -> None:
            attrs, whole, delegates = found.get(command, (set(), False, set()))
            found[command] = (
                attrs | reads.attrs,
                whole or reads.passed_whole,
                    delegates | reads.delegates,
            )

        def descend(statements: list[ast.stmt]) -> None:
            for statement in statements:
                if isinstance(statement, ast.If):
                    matched = False
                    probes = [(var, attr, None) for var in candidates for attr in SELECTOR_ATTRS]
                    probes += [(ns, attr, alias) for alias, (ns, attr) in aliases.items()]
                    for var, attr, alias in probes:
                        selected = _selected_commands(statement.test, var, attr, alias)
                        if not selected:
                            continue
                        matched = True
                        reads = _NamespaceReads(var)
                        for body_statement in statement.body:
                            reads.visit(body_statement)
                        for command in selected:
                            record(command, reads)
                    descend(statement.orelse)
                    if not matched:
                        descend(statement.body)
                elif isinstance(statement, ast.Match):
                    subject = statement.subject
                    var = (
                        subject.value.id
                        if isinstance(subject, ast.Attribute) and isinstance(subject.value, ast.Name)
                        else None
                    )
                    if var is None:
                        continue
                    for case in statement.cases:
                        selected = {
                            node.value
                            for node in ast.walk(case.pattern)
                            if isinstance(node, ast.Constant) and isinstance(node.value, str)
                        }
                        if not selected:
                            continue
                        reads = _NamespaceReads(var)
                        for body_statement in case.body:
                            reads.visit(body_statement)
                        for command in selected:
                            record(command, reads)
                elif isinstance(statement, (ast.Try, ast.With, ast.For, ast.While)):
                    descend(statement.body)
                    descend(list(getattr(statement, "orelse", []) or []))

        descend(function.body)
    return found


def _handler_reads(handler: Any) -> tuple[set[str], bool, set[str]] | None:
    """Namespace attributes read by a ``set_defaults(fn=...)`` handler, plus delegates."""
    try:
        source = inspect.getsource(handler)
        tree = ast.parse(source)
        function = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    except (OSError, TypeError, SyntaxError, StopIteration, IndentationError):
        return None
    var = function.args.args[0].arg if function.args.args else "args"
    reads = _NamespaceReads(var)
    for statement in function.body:
        reads.visit(statement)
    return reads.attrs, reads.passed_whole, reads.delegates



def _function_table(sources: tuple[str, ...]) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Top-level functions of the dispatching modules, by name."""
    table: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for relative in sources:
        tree = ast.parse((REPO_ROOT / relative).read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                table.setdefault(node.name, node)
    return table


def _resolve_delegated_reads(
    delegates: set[tuple[str, int | str]],
    table: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    depth: int = 3,
    seen: frozenset[tuple[str, int | str]] = frozenset(),
) -> set[str]:
    """Namespace attributes read by the handlers a dispatch branch delegates to.

    ``main`` mostly reads nothing itself and hands the namespace straight to a
    per-verb handler, so following the call is what makes the check meaningful
    for those subcommands.
    """
    if depth <= 0:
        return set()
    attrs: set[str] = set()
    for delegate in delegates - seen:
        name, where = delegate
        function = table.get(name)
        if function is None:
            continue
        parameters = [a.arg for a in function.args.args]
        if isinstance(where, int):
            if where >= len(parameters):
                continue
            var = parameters[where]
        else:
            if where not in parameters:
                continue
            var = where
        reads = _NamespaceReads(var)
        for statement in function.body:
            reads.visit(statement)
        attrs |= reads.attrs
        attrs |= _resolve_delegated_reads(reads.delegates, table, depth - 1, seen | {delegate})
    return attrs


# Dispatch sources per CLI. Anything in ARGPARSE_CLIS without an entry here falls
# back to its own module, so adding a CLI above cannot silently skip the dest check.
EXTRA_DISPATCH_SOURCES: dict[str, tuple[str, ...]] = {
    "agentdecompile-corpus": CORPUS_DISPATCH_MODULES,
}


def _module_source(module_name: str) -> str:
    """Repo-relative path of a module's file, for AST scanning."""
    module = importlib.import_module(module_name)
    return str(Path(module.__file__).resolve().relative_to(REPO_ROOT))


ARGPARSE_HANDLER_CASES: tuple[tuple[str, str], ...] = ARGPARSE_CLIS


@pytest.mark.parametrize(
    ("prog", "module_name"),
    ARGPARSE_HANDLER_CASES,
    ids=[case[0] for case in ARGPARSE_HANDLER_CASES],
)
def test_argparse_handlers_only_read_declared_dests(prog: str, module_name: str) -> None:
    """Reading ``args.X`` for an undeclared dest is ``AttributeError`` at dispatch.

    Handlers reached through ``set_defaults(fn=...)`` are read directly; the rest
    are found in the ``if cmd == "..."`` chains of the dispatching modules. A
    subcommand whose handler passes the namespace on whole is checked only as far
    as its own body; the count of those is reported so a green result is not read
    as full coverage.
    """
    root = importlib.import_module(module_name).build_parser()
    action = subparser_action(root)
    if action is None:
        # agentdecompile-reconstruct is a flat parser: every argument is a root
        # flag and main() reads the namespace directly, so there is no per-verb
        # dispatch to cross-check. Skipped out loud rather than omitted from the
        # case list, which is how it went unchecked before.
        pytest.skip(f"{prog} declares no subcommands; no dispatch to cross-check")

    sources = EXTRA_DISPATCH_SOURCES.get(prog) or (_module_source(module_name),)
    table = _function_table(sources)
    dispatch: dict[str, tuple[set[str], bool]] = {}
    delegated: list[str] = []
    for relative in sources:
        for command, (attrs, whole, delegates) in _scan_dispatch(REPO_ROOT / relative).items():
            # Follow the per-verb handler the branch delegates to, so the check
            # sees the reads that actually happen.
            resolved = attrs | _resolve_delegated_reads(delegates, table)
            still_opaque = whole and not resolved - attrs
            known_attrs, known_whole = dispatch.get(command, (set(), False))
            dispatch[command] = (known_attrs | resolved, known_whole or still_opaque)

    root_dests = dests_of(root)
    problems: list[str] = []
    unreachable: list[str] = []
    uninspectable: list[str] = []
    group_dispatched: list[str] = []
    checked = 0

    for name, sub in action.choices.items():
        declared = dests_of(sub) | root_dests
        nested = subparser_action(sub)
        if nested is not None:
            # A group handler dispatches to nested subcommands, whose dests are
            # equally available on the parsed namespace.
            for nested_sub in nested.choices.values():
                declared |= dests_of(nested_sub)

        handler = sub._defaults.get("fn")
        if callable(handler):
            reads = _handler_reads(handler)
            if reads is None:
                uninspectable.append(name)
                continue
            attrs, passed_whole, delegates = reads
            resolved = _resolve_delegated_reads(delegates, table)
            if resolved - attrs:
                passed_whole = False
            attrs |= resolved
        elif name in dispatch:
            attrs, passed_whole = dispatch[name]
        else:
            unreachable.append(name)
            continue
        checked += 1
        if passed_whole:
            delegated.append(name)
        missing = {attr for attr in attrs if attr not in declared and not attr.startswith("_")}
        if missing:
            problems.append(f"{prog} {name}: handler reads args{sorted(missing)}, subparser declares no such dest")

        if nested is not None:
            for nested_name, nested_sub in nested.choices.items():
                nested_handler = nested_sub._defaults.get("fn")
                if not callable(nested_handler):
                    # No dedicated handler: the group's own handler dispatches this
                    # verb, so the group-level check above already covers its reads.
                    group_dispatched.append(f"{name} {nested_name}")
                    continue
                nested_reads = _handler_reads(nested_handler)
                if nested_reads is None:
                    uninspectable.append(f"{name} {nested_name}")
                    continue
                checked += 1
                nested_declared = dests_of(nested_sub) | dests_of(sub) | root_dests
                nested_attrs = nested_reads[0] | _resolve_delegated_reads(nested_reads[2], table)
                nested_missing = {
                    attr for attr in nested_attrs if attr not in nested_declared and not attr.startswith("_")
                }
                if nested_missing:
                    problems.append(
                        f"{prog} {name} {nested_name}: handler reads args{sorted(nested_missing)}, not declared"
                    )

    assert not unreachable, f"{prog} subcommands with no reachable handler: {sorted(unreachable)}"
    assert not problems, "argparse handlers read undeclared dests:\n" + "\n".join(problems)
    # Green here means "no defect visible at this depth", not "fully covered":
    # a handler that hands the whole namespace to a helper is read only as far as
    # its own body. Report the split so the limit travels with the result.
    assert checked, f"{prog}: no handlers were checked, the scan is not covering anything"
    print(
        f"\n{prog}: {checked} handlers scanned, "
        f"{len(delegated)} pass the namespace on whole (body-depth visibility only), "
        f"{len(uninspectable)} with unparseable handlers "
        f"{sorted(uninspectable) if uninspectable else ''}, "
        f"{len(group_dispatched)} nested verbs dispatched by their group handler"
    )

# --------------------------------------------------------------------------- #
# click: the eight repaired commands, pinned and actually executed
# --------------------------------------------------------------------------- #
# Renaming a click parameter name is invisible to users; renaming the option
# string is not. These are the flags the eight repaired commands must keep. The
# binding and duplicate checks above pass happily with a flag missing, so this is
# what catches a lost flag.
REPAIRED_COMMAND_FLAGS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("checkin",): ("-b", "--binary", "-m", "--message", "--keep-checked-out"),
    ("change-processor",): ("-b", "--binary", "--language-id", "--compiler-spec-id"),
    ("dataflow",): ("-b", "--binary", "--function-address", "--start-address", "--variable-name"),
    ("suggest",): ("-b", "--binary", "--suggestion-type", "--address", "--function", "--data-type", "--variable-address"),
    ("open-all-in-code-browser",): ("--folder-path", "--extensions"),
    ("data", "create-label"): ("-b", "--binary", "--name", "--primary"),
    ("match-function",): (
        "-b", "--binary", "--function-identifier", "--target-program-paths",
        "--max-instructions", "--min-similarity", "--propagate-names", "--no-propagate-names",
        "--propagate-tags", "--no-propagate-tags", "--propagate-comments", "--no-propagate-comments",
        "--filter-default-names", "--no-filter-default-names", "--filter-by-tag",
        "--max-functions", "--batch-size",
    ),
    ("function", "run"): (
        "--action", "-b", "--binary", "--function-identifier", "--old-name", "--new-name",
        "--variable-mappings", "--variable-name", "--new-type", "--datatype-mappings",
        "--archive-name", "--create-if-not-exists", "--no-create-if-not-exists",
        "--propagate-program-paths", "--propagate-max-candidates", "--propagate-max-instructions",
    ),
}


@pytest.mark.parametrize(
    "path",
    list(REPAIRED_COMMAND_FLAGS),
    ids=[" ".join(path) for path in REPAIRED_COMMAND_FLAGS],
)
def test_repaired_commands_keep_their_option_strings(path: tuple[str, ...]) -> None:
    """The user-facing flags of the repaired commands are pinned.

    The camelCase-to-snake_case fix changed parameter names only. If a future edit
    drops or renames one of these flags, scripts and docs break silently -- the
    binding and duplicate-declaration checks would both still pass.
    """
    command = click_root()
    for segment in path:
        command = command.commands[segment]
    declared: set[str] = set()
    for param in command.params:
        declared.update(param.opts)
        declared.update(param.secondary_opts)
    missing = set(REPAIRED_COMMAND_FLAGS[path]) - declared
    assert not missing, f"{' '.join(path)} lost option string(s) {sorted(missing)}"


# The wire contract is camelCase (src/agentdecompile_cli/CLAUDE.md). The Python
# parameters are snake_case. These commands translate between the two, so a rename
# that also rewrote a payload key would corrupt the MCP request while every
# introspection check above still passed.
PAYLOAD_INVOCATIONS: tuple[tuple[tuple[str, ...], list[str], tuple[str, ...]], ...] = (
    (("checkin",), ["--keep-checked-out", "-b", "prog"], ("keepCheckedOut", "programPath")),
    (("change-processor",), ["-b", "prog", "--language-id", "x86:LE:32:default"], ("languageId", "programPath")),
    (("dataflow",), ["-b", "prog", "--function-address", "0x1000", "--direction", "forward"],
     ("functionAddress", "programPath")),
    (("suggest",), ["-b", "prog", "--suggestion-type", "variable-name"], ("suggestionType", "programPath")),
    (("data", "create-label"), ["-b", "prog", "--name", "myLabel", "--primary", "0x1000"],
     ("labelName", "setAsPrimary", "addressOrSymbol")),
)


@pytest.mark.parametrize(
    ("path", "argv", "expected_keys"),
    PAYLOAD_INVOCATIONS,
    ids=[" ".join(case[0]) for case in PAYLOAD_INVOCATIONS],
)
def test_repaired_commands_send_camelcase_payload_keys(
    monkeypatch: pytest.MonkeyPatch,
    path: tuple[str, ...],
    argv: list[str],
    expected_keys: tuple[str, ...],
) -> None:
    """Run each repaired command and inspect the request it would send.

    The transport is replaced, so no server is contacted and no port is opened.
    This is the one check here that executes a command body: it proves the
    TypeError is gone in practice, not just that the names line up.
    """
    from click.testing import CliRunner

    from agentdecompile_cli import cli as cli_module

    captured: dict[str, Any] = {}

    async def fake_call(ctx: click.Context, tool: str, **kwargs: Any) -> None:
        captured["tool"] = tool
        captured["payload"] = kwargs

    monkeypatch.setattr(cli_module, "_call", fake_call)
    result = CliRunner().invoke(cli_module.main, list(path) + argv, catch_exceptions=True)

    assert not isinstance(result.exception, TypeError), (
        f"{' '.join(path)} raised TypeError binding its callback: {result.exception}"
    )
    assert "payload" in captured, (
        f"{' '.join(path)} never reached the transport; exit={result.exit_code} "
        f"exception={result.exception!r} output={result.output[:400]}"
    )
    payload_keys = set(captured["payload"])
    snake_keys = {key for key in payload_keys if "_" in key}
    assert not snake_keys, f"{' '.join(path)} sent snake_case wire key(s) {sorted(snake_keys)}"
    missing = set(expected_keys) - payload_keys
    assert not missing, f"{' '.join(path)} omitted wire key(s) {sorted(missing)} from {sorted(payload_keys)}"

# --------------------------------------------------------------------------- #
# coverage floors and the output-format flag
# --------------------------------------------------------------------------- #
# Counts observed on the tree these checks were written against. They are floors
# and a ceiling, not exact pins: commands get added, so a modest drift is fine,
# but a collapse means the checks above stopped walking anything and would pass on
# an empty tree.
MIN_CLICK_LEAF_COMMANDS = 150
MIN_ARGPARSE_PARSERS = 100
# Commands whose callback takes **kwargs absorb any parameter click passes, so the
# unexpected-parameter check cannot fail for them. Every such command today is
# machine-generated: `tool_command` from _create_dynamic_commands, `callback` from
# _derive_convenience_commands. Those two grow with the tool registry, so counting
# them is a nuisance rather than a guard. What matters is that no HAND-WRITTEN
# command drifts into the exemption, because that is the surface where the eight
# TypeErrors lived.
GENERATED_CALLBACK_NAMES = frozenset({"tool_command", "callback"})


def _click_leaves() -> list[tuple[str, click.Command]]:
    return [
        (path, command)
        for path, command in walk_click(click_root(), "agentdecompile")
        if not isinstance(command, click.Group) and command.callback is not None
    ]


def test_click_surface_has_not_collapsed() -> None:
    """The binding and duplicate checks assert on a collected list.

    An empty list satisfies them, so a registration failure that dropped every
    command would read as a clean pass. This is the floor that makes them mean
    something.
    """
    leaves = _click_leaves()
    assert len(leaves) >= MIN_CLICK_LEAF_COMMANDS, (
        f"only {len(leaves)} leaf commands walked, expected at least "
        f"{MIN_CLICK_LEAF_COMMANDS}; command registration may have failed"
    )


def test_only_generated_commands_escape_the_binding_check() -> None:
    """No hand-written command may take **kwargs.

    A **kwargs callback cannot fail the unexpected-parameter check, so a
    hand-written command that grows one becomes unguarded against exactly the
    defect this file exists to catch.

    The generated commands stay exempt and are NOT broadly covered elsewhere:
    of the 128, only `export` is ever invoked by a test, and only to check that
    `-f` stays out of the payload. The shortcut half of them is covered by
    test_derived_shortcuts_can_reach_their_run_command below; the dynamic half
    is not, which is a known gap rather than a claim of coverage.
    """
    hand_written_exempt: list[str] = []
    for path, command in _click_leaves():
        signature = callback_signature(command.callback)
        if signature is None or not signature[2]:
            continue
        target = getattr(command.callback, "__wrapped__", command.callback)
        if getattr(target, "__name__", "") not in GENERATED_CALLBACK_NAMES:
            hand_written_exempt.append(f"{path} (callback {getattr(target, '__name__', '?')})")
    assert not hand_written_exempt, (
        "hand-written commands take **kwargs and so cannot fail the "
        f"unexpected-parameter check: {hand_written_exempt}"
    )


def test_every_click_owned_leaf_accepts_the_output_format_flag() -> None:
    """`-f` selects output format on every Click-owned command.

    Four commands own a `format` parameter of their own, so they take `-f` as a
    separate short-only option. Skipping that step once removed `-f` from those
    four and turned `agentdecompile export -f json` into "No such option", which
    no structural check noticed. Argparse bridge leaves are deliberately exempt:
    their byte-exact parser forwards `-f` to the embedded CLI instead.
    """
    missing = [
        path
        for path, command in _click_leaves()
        if not getattr(command, "BRIDGED", False)
        and not any("-f" in param.opts for param in command.params)
    ]
    assert not missing, f"commands that do not accept -f: {missing}"


def test_argparse_bridge_leaves_forward_output_format_flag_byte_exact() -> None:
    bridged = [(path, command) for path, command in _click_leaves() if getattr(command, "BRIDGED", False)]
    assert bridged, "no argparse bridge leaves found"
    forwarded = ["-f", "json", "--", "--literal"]
    for path, command in bridged:
        ctx = click.Context(command, info_name=path.split()[-1])
        assert command.parse_args(ctx, list(forwarded)) == [], path
        assert ctx.params["args"] == tuple(forwarded), path


def test_output_format_flag_never_reaches_the_request() -> None:
    """`-f` is CLI presentation and must not be sent to the server.

    On the four commands that own a `format` parameter, the short flag has to stay
    out of the payload or it would overwrite the tool's own format value.
    """
    from click.testing import CliRunner

    from agentdecompile_cli import cli as cli_module

    captured: dict[str, Any] = {}

    async def fake_call(ctx: click.Context, tool: str, **kwargs: Any) -> None:
        captured["payload"] = kwargs
        captured["resolved_format"] = cli_module._fmt(ctx)

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(cli_module, "_call", fake_call)
        result = CliRunner().invoke(
            cli_module.main,
            ["export", "-f", "json", "--program-path", "p", "--output-path", "o"],
        )
    finally:
        monkey.undo()

    assert result.exit_code == 0, f"export -f json failed: {result.exception!r} {result.output[:300]}"
    assert captured.get("resolved_format") == "json", (
        f"-f json did not select the output format (got {captured.get('resolved_format')!r})"
    )
    assert "format" not in captured.get("payload", {}), (
        "the -f output-format flag leaked into the tool request payload"
    )


def test_argparse_surface_has_not_collapsed() -> None:
    """Floor for the argparse help/parse sweep, for the same reason as above."""
    total = 0
    for prog, module_name in ARGPARSE_CLIS:
        root = importlib.import_module(module_name).build_parser()
        total += sum(1 for _ in walk_argparse(root, prog))
    assert total >= MIN_ARGPARSE_PARSERS, (
        f"only {total} argparse parsers walked, expected at least {MIN_ARGPARSE_PARSERS}"
    )

def _derived_shortcuts() -> list[tuple[str, click.Command, dict[str, Any]]]:
    """Every shortcut built by `_derive_convenience_commands`, with its closure.

    The shortcut's callback closes over the `run` command it forwards to, the
    selector it pins, and the `omitted_values` dict it splats in. Those three are
    what decide whether the forward can bind.
    """
    found: list[tuple[str, click.Command, dict[str, Any]]] = []
    for path, command in _click_leaves():
        inner = getattr(command.callback, "__wrapped__", command.callback)
        try:
            nonlocals = inspect.getclosurevars(inner).nonlocals
        except (TypeError, ValueError):
            continue
        if {"run_command", "selector_name", "omitted_values"} <= set(nonlocals):
            found.append((path, command, nonlocals))
    return found


def test_derived_shortcuts_can_reach_their_run_command() -> None:
    """A shortcut forwards `omitted_options` by name into its `run` command.

    `_derive_convenience_commands` splats `{name: None for name in
    omitted_options}` into `ctx.invoke(run_command, ...)`, and that frozenset is
    maintained by hand at ten call sites. A name left in it after the `run`
    command's parameter was renamed makes every shortcut in that group raise
    `TypeError: <run>() got an unexpected keyword argument '<stale>'` -- the same
    failure as the eight commands this file was written for, one frame deeper.
    The binding check cannot see it: these callbacks take **values.
    """
    shortcuts = _derived_shortcuts()
    assert shortcuts, "no derived shortcuts found; the introspection no longer matches"
    problems: list[str] = []
    for path, command, nonlocals in shortcuts:
        run_command = nonlocals["run_command"]
        forwarded = set(nonlocals["omitted_values"])
        forwarded.add(nonlocals["selector_name"])
        forwarded.update(param.name for param in command.params if param.expose_value)
        signature = callback_signature(run_command.callback)
        if signature is None:
            continue
        accepted, _required, accepts_kwargs = signature
        if accepts_kwargs:
            continue
        unexpected = forwarded - accepted
        if unexpected:
            problems.append(
                f"{path} forwards {sorted(unexpected)} to "
                f"{getattr(run_command, 'name', '?')}, which accepts no such parameter"
            )
    assert not problems, (
        "derived shortcuts cannot bind their run command:\n" + "\n".join(problems)
    )



def test_dynamic_command_params_come_from_the_tool_registry() -> None:
    """Every parameter of a generated command must trace back to its tool.

    The 68 commands built by `_create_dynamic_commands` take **kwargs and forward
    them straight into the request, so a parameter name that does not match the
    registry is sent to the server as-is: the option still parses, the command
    still exits 0, and the payload carries a key the tool does not know. That is
    silent corruption rather than a failure, and no other check here would see it.
    """
    from agentdecompile_cli.cli import _supported_cli_tool_params, to_snake_case
    from agentdecompile_cli.registry import TOOL_PARAMS

    root = click_root()
    problems: list[str] = []
    checked = 0
    for name, command in root.commands.items():
        if isinstance(command, click.Group):
            continue
        inner = getattr(command.callback, "__wrapped__", command.callback)
        if getattr(inner, "__name__", "") != "tool_command" or name not in TOOL_PARAMS:
            continue
        checked += 1
        expected = {to_snake_case(param) for param in _supported_cli_tool_params(name)}
        exposed = {param.name for param in command.params if param.expose_value}
        # No exclusions: the connection and output-format flags _add_global_options
        # attaches do not expose values, so everything exposed must be a tool
        # parameter.
        undeclared = exposed - expected
        if undeclared:
            problems.append(f"{name} exposes {sorted(undeclared)}, absent from its registry parameters")
    assert checked, "no generated tool commands found; the introspection no longer matches"
    assert not problems, (
        "generated commands expose parameters the tool registry does not declare:\n"
        + "\n".join(problems)
    )


# --------------------------------------------------------------------------- #
# per-command connection and output flags on generated commands
# --------------------------------------------------------------------------- #
def _run_generated(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], obj: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Invoke a generated command with the network layer stubbed.

    Stubs `_execute_tool_call`, below `_call_raw`, so the payload recorded is the
    one that would go on the wire and `_call`'s own rendering still runs.
    """
    from click.testing import CliRunner

    from agentdecompile_cli import cli as cli_module

    seen: dict[str, Any] = {}

    async def fake_execute(ctx: click.Context, tool: str, payload: dict[str, Any], client_override: Any = None) -> Any:
        opts = cli_module._get_opts(ctx)
        seen["payload"] = dict(payload)
        seen["target"] = {key: opts.get(key) for key in ("host", "port", "server_url")}
        seen["explicit"] = opts.get("backend_cli_explicit")
        seen["local_mode"] = opts.get("local_mode")
        seen["render"] = cli_module._fmt(ctx)
        return {"content": [{"type": "text", "text": "BODY"}], "isError": False}

    monkeypatch.delenv("AGENTDECOMPILE_LOCAL_MODE", raising=False)
    monkeypatch.setattr(cli_module, "_execute_tool_call", fake_execute)
    result = CliRunner().invoke(cli_module.main, argv, obj=obj)
    assert result.exit_code == 0, f"{argv} failed: {result.exception!r} {result.output[:300]}"
    return seen


_TOOL_ARGS = ["--program-path", "p", "--function-identifier", "main"]


@pytest.mark.parametrize(
    "flags",
    [["--host", "10.0.0.5", "--port", "9999"], ["--server-url", "http://example.invalid:1/mcp"]],
    ids=["host-port", "server-url"],
)
def test_per_command_connection_flags_route_like_top_level_ones(
    flags: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`decompile-function --port 9999` must connect where `--port 9999 decompile-function` does.

    Generated commands advertise --host/--port/--server-url in their help. They
    used to be forwarded into the tool request while the connection kept the root
    defaults, so the per-command form reached 127.0.0.1:8080 regardless.
    """
    per_command = _run_generated(monkeypatch, ["decompile-function", *flags, *_TOOL_ARGS])
    top_level = _run_generated(monkeypatch, [*flags, "decompile-function", *_TOOL_ARGS])
    assert per_command["target"] == top_level["target"], (
        f"per-command {flags} connects to {per_command['target']}, top-level form to {top_level['target']}"
    )
    assert per_command["explicit"] is True, "a named backend must be marked explicit"
    assert per_command["local_mode"] is False, "a named backend must not fall back to local execution"
    leaked = {"host", "port", "server_url", "serverUrl"} & set(per_command["payload"])
    assert not leaked, f"connection flags leaked into the tool request: {sorted(leaked)}"


def test_per_command_output_format_matches_top_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """`decompile-function -f json` must render what `-f json decompile-function` renders.

    The generated form used to send `format` to the server while the client kept
    rendering text, and its default of "text" overrode the markdown default that
    `_call_raw` documents for every request.
    """
    per_command = _run_generated(monkeypatch, ["decompile-function", "-f", "json", *_TOOL_ARGS])
    top_level = _run_generated(monkeypatch, ["-f", "json", "decompile-function", *_TOOL_ARGS])
    plain = _run_generated(monkeypatch, ["decompile-function", *_TOOL_ARGS])
    assert per_command["render"] == top_level["render"] == "json", (
        f"per-command renders {per_command['render']!r}, top-level {top_level['render']!r}"
    )
    assert per_command["payload"].get("responseFormat") == top_level["payload"].get("responseFormat") == "json"
    assert plain["payload"].get("responseFormat") == "markdown", (
        "generated commands must keep the documented markdown default, "
        f"got {plain['payload'].get('responseFormat')!r}"
    )


def test_per_command_connection_flag_keeps_preexisting_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pre-existing obj["local_mode"] must survive a per-command --port override.

    `main()` OR's a fresh --local flag with `existing_obj.get("local_mode")` when
    computing its own `local_mode`, but the per-command override callback used to
    read only `root_ctx.params.get("local_mode")` (this invocation's --local flag),
    dropping a pre-existing obj's local_mode. Both argv orders must agree.
    """
    obj = {"local_mode": True}
    per_command = _run_generated(
        monkeypatch, ["decompile-function", "--port", "9999", *_TOOL_ARGS], obj=dict(obj)
    )
    top_level = _run_generated(
        monkeypatch, ["--port", "9999", "decompile-function", *_TOOL_ARGS], obj=dict(obj)
    )
    assert per_command["local_mode"] is True, (
        f"per-command form dropped pre-existing local_mode: {per_command['local_mode']!r}"
    )
    assert top_level["local_mode"] is True, (
        f"top-level form dropped pre-existing local_mode: {top_level['local_mode']!r}"
    )
    # The no-obj, no --local, explicit-backend case is already covered by
    # test_per_command_connection_flags_route_like_top_level_ones (local_mode False).


def test_per_command_connection_flag_drops_auto_only_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pre-existing obj whose local_mode was only auto-derived must not survive.

    `local_mode_requested: False` records that the earlier run's local_mode came
    from auto-local mode, not an explicit ask. `main()` used to fall back to
    `existing_obj.get("local_mode", False)` (True here) instead of
    `existing_obj.get("local_mode_requested", ...)`, so an explicit per-command
    backend flag failed to clear an auto-only local_mode.
    """
    obj = {"local_mode": True, "local_mode_requested": False}
    result = _run_generated(
        monkeypatch, ["decompile-function", "--port", "9999", *_TOOL_ARGS], obj=dict(obj)
    )
    assert result["local_mode"] is False, (
        f"per-command flag should have cleared auto-only local_mode: {result['local_mode']!r}"
    )
