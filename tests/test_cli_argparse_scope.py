"""Guard against cross-scope duplicate options in the argparse CLIs.

Defect class: an option (same option string, OR a different option string
writing the same ``dest``) declared on a parent parser AND on one of its
descendant subparsers. Argparse applies each subparser's own defaults to the
namespace after the parent has already parsed, so a value supplied in the
*parent* position (``--x V sub ...``) is silently overwritten by the
subparser's default unless that subparser's action uses
``default=argparse.SUPPRESS``. The user-visible symptom is a flag the
top-level ``--help`` advertises that has no effect once a subcommand follows
it.

A structural test walks every parser tree of the four argparse CLIs
(``agentdecompile-recover``, ``agentdecompile-corpus`` -- which also pulls in
``corpus/kx_cli.py`` and ``corpus/mizuchi_tools_cli.py`` --
``agentdecompile-reconstruct``, and ``adgrid``, including adgrid's nested
subparsers) and fails on any parent/descendant collision whose descendant does
not use ``argparse.SUPPRESS``. This covers three ways a descendant scope can
write the same dest as an ancestor: a regular ``add_argument`` action, a
subparsers action's own ``dest`` (commonly ``cmd``/``command``), and a bare
``set_defaults`` call.

Sweeping all four CLIs at commit time found zero real instances of the
defect, so there is nothing to fix and no behavioral fixture tests are
needed here -- only the structural guard, plus a self-test proving the guard
does catch a real collision when one exists (``test_guard_catches_a_real_collision``).

``ARGPARSE_CLIS`` and ``walk_argparse`` are imported from
``tests.test_cli_contract`` rather than redefined here, so the two files
share one list of CLIs and one tree-walking implementation.

Everything here builds parser objects and calls ``parse_args`` on them. No
command body ever runs, no process starts, no port opens, and nothing is
written to disk, so these checks are safe under the recovery-operation
constraints in AGENTS.md.
"""

from __future__ import annotations

import argparse

import pytest

from tests.test_cli_contract import ARGPARSE_CLIS, walk_argparse

pytestmark = pytest.mark.unit


def _own_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """Actions declared directly on this parser, including its own subparsers
    action (its ``dest`` -- often ``cmd``/``command`` -- is itself written into
    the namespace and can collide with an ancestor's dest), excluding ``help``.
    """
    return [action for action in parser._actions if action.dest != "help"]


def _own_set_defaults(parser: argparse.ArgumentParser) -> dict[str, object]:
    """``dest -> value`` pairs from this parser's own ``set_defaults`` calls only.

    ``parser._defaults`` also gets populated by each action's own default
    during normal argparse bookkeeping in some versions, so this restricts to
    dests that are *not* already covered by one of this parser's own actions
    -- those are handled by ``_own_actions`` instead.
    """
    action_dests = {a.dest for a in parser._actions}
    return {dest: value for dest, value in parser._defaults.items() if dest not in action_dests}


class _Write:
    """One thing a parser's own scope writes into the namespace.

    Covers three sources that can each independently clobber a parent value:
    a regular action (``add_argument``), the parser's own subparsers action
    (its ``dest``, commonly ``cmd``/``command``, is written too), and a bare
    ``set_defaults`` call with no backing action.
    """

    __slots__ = ("dest", "option_strings", "default", "suppressible", "describe")

    def __init__(self, dest: str, option_strings: list[str], default: object, suppressible: bool, describe: str) -> None:
        self.dest = dest
        self.option_strings = option_strings
        self.default = default
        self.suppressible = suppressible
        self.describe = describe


def _own_writes(parser: argparse.ArgumentParser) -> list[_Write]:
    writes = [
        _Write(a.dest, list(a.option_strings), a.default, True, "action")
        for a in _own_actions(parser)
        if a.dest and a.dest != argparse.SUPPRESS
    ]
    writes += [
        _Write(dest, [], value, False, "set_defaults")
        for dest, value in _own_set_defaults(parser).items()
    ]
    return writes


def find_scope_collisions(root: argparse.ArgumentParser, label: str) -> list[str]:
    """Report every parent/descendant write pair that collides on option string or dest.

    A collision from a regular action is only a *defect* (reported) when the
    descendant's default is not ``argparse.SUPPRESS`` -- that is the case
    where the parent's parsed value gets clobbered. A descendant action using
    SUPPRESS is the standard fix and is not reported. A ``set_defaults`` write
    has no SUPPRESS equivalent -- it always overwrites -- so any collision
    involving one is reported unconditionally.
    """
    nodes = list(walk_argparse(root, label))
    problems: list[str] = []
    for path, parser in nodes:
        ancestors = [(p, ap) for p, ap in nodes if path.startswith(p + " ") and p != path]
        for write in _own_writes(parser):
            for ancestor_path, ancestor_parser in ancestors:
                for ancestor_write in _own_writes(ancestor_parser):
                    same_optstr = set(write.option_strings) & set(ancestor_write.option_strings)
                    same_dest = write.dest == ancestor_write.dest
                    if not (same_optstr or same_dest):
                        continue
                    if write.suppressible and write.default is argparse.SUPPRESS:
                        continue  # standard fix already applied
                    reason = "option string" if same_optstr else "dest"
                    problems.append(
                        f"{label}: {ancestor_path!r} writes dest {ancestor_write.dest!r} via "
                        f"{ancestor_write.describe} (options={ancestor_write.option_strings or None}, "
                        f"default={ancestor_write.default!r}) and descendant {path!r} redeclares it via "
                        f"{write.describe} (options={write.option_strings or None}, dest={write.dest!r}, "
                        f"default={write.default!r}) -- same {reason}, descendant does not use "
                        f"argparse.SUPPRESS, so the parent value is lost"
                    )
    return problems


def _build_parser(module_name: str) -> argparse.ArgumentParser:
    import importlib

    module = importlib.import_module(module_name)
    return module.build_parser()


# --------------------------------------------------------------------------- #
# structural guard
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("label,module_name", ARGPARSE_CLIS)
def test_no_cross_scope_duplicate_options(label: str, module_name: str) -> None:
    parser = _build_parser(module_name)
    problems = find_scope_collisions(parser, label)
    assert not problems, "cross-scope duplicate options found:\n" + "\n".join(problems)


def test_guard_catches_a_real_collision() -> None:
    """Self-test: prove the structural guard actually detects the defect class.

    Builds a tiny synthetic parser tree with a root ``--label`` and a
    subparser ``--label`` (default not SUPPRESS) that shadows it, and checks
    the guard reports it. This does not touch any of the four real CLIs; it
    only proves ``find_scope_collisions`` is not vacuously passing.
    """
    root = argparse.ArgumentParser(prog="synthetic")
    root.add_argument("--label", default="root-default")
    sub = root.add_subparsers(dest="cmd")
    child = sub.add_parser("add-binary")
    child.add_argument("--label", default="")  # shadows the root's --label

    problems = find_scope_collisions(root, "synthetic")
    assert problems, "guard failed to catch a real parent/descendant collision"

    # And prove the underlying argparse symptom the guard exists to catch:
    # the parent-position value is silently discarded.
    ns = root.parse_args(["--label", "custom", "add-binary"])
    assert ns.label == "", (
        "expected the synthetic collision to demonstrate value loss (dest reset to "
        f"child default ''), got {ns.label!r} -- if this changes, argparse's "
        "subparser-default-clobbers-parent behavior changed and this self-test "
        "needs to be revisited"
    )
