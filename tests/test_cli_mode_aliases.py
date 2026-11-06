"""Mode-alias resolution must be deterministic and must not clobber a tool's own parameters.

Finding F1: `_extract_argument_value` used to resolve a missing "mode" value by
scanning `MODE_PARAM_ALIASES`, which was a `frozenset`. Set iteration order
depends on `PYTHONHASHSEED`, so which alias "won" when a payload carried more
than one (e.g. both "action" and "type") was nondeterministic. Worse,
`_merge_tools_list_params` unconditionally collapsed a tool's own real
parameter (manage-bookmarks'/manage-structures' "type", acquisition-query's
"action", svr-admin's "command") into a duplicate "mode" entry, so those
parameters could never be resolved under their own name at all.

These tests prove, from outside the process, that:
(a) the four repro shapes from the bug hunt (bookmarks curated command,
    structures curated command, `tool` JSON form, `tool-seq` JSON form) send a
    stable wire payload under every hash seed;
(b) `ToolRegistry._extract_argument_value` / `parse_arguments` resolve
    deterministically and never let a tool's own declared parameter feed
    "mode";
(c) the alias-resolution machinery never iterates a bare set/frozenset.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

# Full 0-7 sweep confirmed the bug: seeds 1, 3, 4, 5, 6 sent the wrong "mode"
# value before the fix; seeds 0, 2, 7 happened to land on the right one. The
# subprocess matrix below is the expensive part (one interpreter + full CLI
# import per case), so it only re-checks a mix of previously-bad and
# previously-good seeds; the cheap in-process registry tests further down
# still sweep the full MODE_PARAM_PRECEDENCE space deterministically.
HASH_SEEDS: tuple[str, ...] = ("1", "4", "0", "2")

# Executed in a fresh subprocess per seed: PYTHONHASHSEED is read once at
# interpreter start, so it cannot be varied within a single process. The
# network transport is stubbed by monkeypatching `_execute_tool_call`
# (async, `(ctx, tool, payload, client_override=None)`), matching the
# reproduction recipe from the bug hunt. Nothing here reaches the network.
_SUBPROCESS_HARNESS = r"""
import contextlib
import json
import sys

from click.testing import CliRunner

import agentdecompile_cli.cli as climod


async def _fake_execute_tool_call(ctx, tool, payload, client_override=None):
    print("WIRE_PAYLOAD_JSON " + json.dumps(payload, sort_keys=True))
    return {"content": [{"type": "text", "text": "ok"}], "isError": False}


climod._execute_tool_call = _fake_execute_tool_call

# `tool-seq` opens its own MCP client up front (`_tool_sequence_client`),
# independent of `_execute_tool_call`, and that client construction is what
# actually performs the connection attempt. Stub the whole context manager so
# no socket/DNS activity happens; `client_override=None` is fine since
# `_execute_tool_call` above is fully stubbed and ignores it.
@contextlib.asynccontextmanager
async def _fake_tool_sequence_client(ctx):
    yield None


climod._tool_sequence_client = _fake_tool_sequence_client

runner = CliRunner()
argv = json.loads(sys.argv[1])
result = runner.invoke(climod.main, argv)
if result.exception is not None and not isinstance(result.exception, SystemExit):
    raise result.exception
print(result.output, end="")
"""


def _run_cli_in_subprocess(argv: list[str], hash_seed: str) -> dict:
    """Invoke the CLI with a stubbed transport in a fresh subprocess pinned to `hash_seed`.

    Returns the JSON wire payload the (stubbed) tool call would have sent.
    """
    env = {
        "PYTHONHASHSEED": hash_seed,
        "PYTHONPATH": str(SRC_ROOT),
        "PATH": __import__("os").environ.get("PATH", ""),
        "HOME": __import__("os").environ.get("HOME", ""),
        "TMPDIR": __import__("os").environ.get("TMPDIR", "/tmp"),
    }
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_HARNESS, json.dumps(argv)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed (seed={hash_seed}): stdout={proc.stdout!r} stderr={proc.stderr!r}"
    for line in proc.stdout.splitlines():
        if line.startswith("WIRE_PAYLOAD_JSON "):
            return json.loads(line[len("WIRE_PAYLOAD_JSON ") :])
    raise AssertionError(f"no wire payload captured (seed={hash_seed}): stdout={proc.stdout!r} stderr={proc.stderr!r}")


# ---------------------------------------------------------------------------
# (a) End-to-end: every repro shape from the bug hunt, across hash seeds.
# ---------------------------------------------------------------------------

REPRO_CASES: dict[str, list[str]] = {
    "bookmarks_curated_shortcut": [
        "--server-url", "http://stub:1",
        "bookmarks", "set", "--type", "Note", "--address-or-symbol", "0x1",
    ],
    "structures_curated_run": [
        "--server-url", "http://stub:1",
        "structures", "run", "--action", "create", "--type", "union", "--name", "Foo",
    ],
    "tool_json_form": [
        "--server-url", "http://stub:1",
        "tool", "manage-bookmarks",
        json.dumps({"action": "set", "type": "Note", "addressOrSymbol": "0x1"}),
    ],
    "generated_manage_bookmarks_command": [
        "--server-url", "http://stub:1",
        "manage-bookmarks", "--mode", "set", "--type", "Note", "--address-or-symbol", "0x1",
    ],
}


@pytest.mark.parametrize("hash_seed", HASH_SEEDS)
@pytest.mark.parametrize("case_name", sorted(REPRO_CASES))
def test_wire_payload_is_stable_across_hash_seeds(case_name: str, hash_seed: str) -> None:
    payload = _run_cli_in_subprocess(REPRO_CASES[case_name], hash_seed)

    if case_name == "structures_curated_run":
        assert payload["mode"] == "create", f"seed={hash_seed} payload={payload}"
        assert payload["type"] == "union", f"seed={hash_seed} payload={payload}"
    else:
        assert payload["mode"] == "set", f"seed={hash_seed} payload={payload}"
        assert payload["type"] == "Note", f"seed={hash_seed} payload={payload}"


@pytest.mark.parametrize("hash_seed", HASH_SEEDS)
def test_tool_seq_wire_payload_is_stable_across_hash_seeds(hash_seed: str) -> None:
    # Step key is "name" (see `_run_parsed_tool_sequence` / `tool_seq_cmd` in
    # cli.py: `name = step.get("name")`), not "tool".
    seq = json.dumps([{"name": "manage-bookmarks", "arguments": {"action": "set", "type": "Note", "addressOrSymbol": "0x1"}}])
    argv = ["--server-url", "http://stub:1", "tool-seq", seq]
    payload = _run_cli_in_subprocess(argv, hash_seed)
    assert payload["mode"] == "set", f"seed={hash_seed} payload={payload}"
    assert payload["type"] == "Note", f"seed={hash_seed} payload={payload}"


# ---------------------------------------------------------------------------
# (b) Resolution-order unit tests directly against the registry.
# ---------------------------------------------------------------------------


def test_registry_parse_arguments_prefers_mode_over_every_other_alias() -> None:
    from agentdecompile_cli.registry import MODE_PARAM_PRECEDENCE, tool_registry

    payload = {alias: f"VAL_{alias}" for alias in MODE_PARAM_PRECEDENCE}
    parsed = tool_registry.parse_arguments(payload, "get-references")
    assert parsed["mode"] == "VAL_mode"


def test_registry_parse_arguments_mode_alias_precedence_is_deterministic_without_mode_present() -> None:
    """action beats operation beats command ... beats type, with no literal "mode" key present."""
    from agentdecompile_cli.registry import MODE_PARAM_PRECEDENCE, tool_registry

    non_mode_aliases = [a for a in MODE_PARAM_PRECEDENCE if a != "mode"]
    for i, winner in enumerate(non_mode_aliases):
        payload = {alias: f"VAL_{alias}" for alias in non_mode_aliases[i:]}
        parsed = tool_registry.parse_arguments(payload, "get-references")
        assert parsed["mode"] == f"VAL_{winner}", (
            f"expected {winner!r} to win resolution over {non_mode_aliases[i + 1:]}, got {parsed.get('mode')!r}"
        )


def test_bookmark_type_never_becomes_mode_and_action_always_does() -> None:
    """The exact F1 shape: "type" (a real manage-bookmarks parameter) must never win over "action"."""
    from agentdecompile_cli.registry import tool_registry

    payload = {"action": "set", "type": "Note", "addressOrSymbol": "0x1"}
    parsed = tool_registry.parse_arguments(payload, "manage-bookmarks")
    assert parsed["mode"] == "set"
    assert parsed["type"] == "Note"


def test_structures_type_never_becomes_mode() -> None:
    from agentdecompile_cli.registry import tool_registry

    payload = {"action": "create", "type": "union", "name": "Foo"}
    parsed = tool_registry.parse_arguments(payload, "manage-structures")
    assert parsed["mode"] == "create"
    assert parsed["type"] == "union"


def test_bookmark_type_alone_is_not_repurposed_as_mode() -> None:
    """With no other selector present, a bookmark's own "type" must not be scavenged as "mode" either."""
    from agentdecompile_cli.registry import tool_registry

    payload = {"type": "Note", "addressOrSymbol": "0x1"}
    parsed = tool_registry.parse_arguments(payload, "manage-bookmarks")
    assert parsed.get("mode") is None
    assert parsed["type"] == "Note"


@pytest.mark.parametrize(
    ("tool_name", "real_param", "value"),
    [
        ("acquisition-query", "action", "inspect"),
        ("svr-admin", "command", "list"),
    ],
)
def test_tools_with_a_single_mode_alias_shaped_param_keep_their_own_name(
    tool_name: str, real_param: str, value: str,
) -> None:
    """acquisition-query's "action" and svr-admin's "command" are each that tool's only
    selector-shaped field (no separate "mode"); they must resolve under their own name,
    not be silently renamed to "mode" by TOOLS_LIST.md-derived merging."""
    from agentdecompile_cli.registry import tool_registry

    parsed = tool_registry.parse_arguments({real_param: value}, tool_name)
    assert parsed.get(real_param) == value
    assert parsed.get("mode") is None


# ---------------------------------------------------------------------------
# (c) Generic structural check: resolution never iterates a bare set/frozenset.
# ---------------------------------------------------------------------------


def test_mode_param_precedence_is_an_ordered_sequence_containing_every_alias() -> None:
    from agentdecompile_cli.registry import MODE_PARAM_ALIASES, MODE_PARAM_PRECEDENCE

    assert isinstance(MODE_PARAM_PRECEDENCE, (tuple, list)), (
        "MODE_PARAM_PRECEDENCE must be an ordered sequence, not a set/frozenset, "
        "or its iteration order depends on PYTHONHASHSEED"
    )
    assert not isinstance(MODE_PARAM_PRECEDENCE, (set, frozenset))
    assert len(MODE_PARAM_PRECEDENCE) == len(set(MODE_PARAM_PRECEDENCE)), "no duplicate aliases"
    assert MODE_PARAM_PRECEDENCE[0] == "mode", "mode itself must take precedence over every synonym"
    assert set(MODE_PARAM_PRECEDENCE) == set(MODE_PARAM_ALIASES), (
        "every MODE_PARAM_ALIASES member must appear exactly once in the precedence order"
    )


def test_extract_argument_value_source_iterates_the_precedence_tuple_not_a_set() -> None:
    """Static guard: the resolution loop must read MODE_PARAM_PRECEDENCE, not MODE_PARAM_ALIASES."""
    import ast

    from agentdecompile_cli import registry as registry_module

    source = ast.parse(Path(registry_module.__file__).read_text(encoding="utf-8"))
    method = None
    for node in ast.walk(source):
        if isinstance(node, ast.FunctionDef) and node.name == "_extract_argument_value":
            method = node
            break
    assert method is not None, "_extract_argument_value not found"

    iterated_names: set[str] = set()
    for node in ast.walk(method):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Name):
            iterated_names.add(node.iter.id)

    assert "MODE_PARAM_ALIASES" not in iterated_names, (
        "resolution must not iterate MODE_PARAM_ALIASES directly (it is a frozenset; "
        "order depends on PYTHONHASHSEED) -- iterate MODE_PARAM_PRECEDENCE instead"
    )
    assert "MODE_PARAM_PRECEDENCE" in iterated_names
