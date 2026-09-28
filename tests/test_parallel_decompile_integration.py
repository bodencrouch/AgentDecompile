"""Live PyGhidra parity test for the private parallel decompiler pool."""

from __future__ import annotations

import os
from pathlib import Path
import warnings

import pytest

from agentdecompile_cli.mcp_utils.parallel_decompile import batch_candidates, decompile_functions, serial_decompile_one

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).parent / "fixtures" / "test_x86_64"


def _ghidra_project_location(tmp_path: Path) -> Path:
    """Keep Ghidra projects out of dot-prefixed worktree paths.

    Ghidra's ``ProjectLocator`` rejects any path element starting with ``.``.
    The native SDK worktree lives below ``.claude/worktrees``, so a normal
    pytest ``tmp_path`` is not a valid project location on this checkout.
    """
    repo_root = Path(__file__).resolve().parents[1]
    for parent in (repo_root, *repo_root.parents):
        if parent.name == ".claude":
            checkout_root = parent.parent
            location = checkout_root.with_name(f"{checkout_root.name}-native-out") / "parallel-integration" / "projects" / tmp_path.name
            location.mkdir(parents=True, exist_ok=True)
            return location
    return tmp_path


@pytest.mark.skipif(not os.environ.get("GHIDRA_INSTALL_DIR"), reason="GHIDRA_INSTALL_DIR required")
def test_parallel_matches_serial_and_disposes(ghidra_initialized, tmp_path: Path) -> None:
    import pyghidra

    project_location = _ghidra_project_location(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        context = pyghidra.open_program(str(FIXTURE), project_location=str(project_location), project_name="parallel", analyze=True)
    with context as flat:
        program = flat.getCurrentProgram()
        functions = batch_candidates(program, limit=2)
        assert len(functions) == 2
        expected = {result.addr: result.c_text for result in (serial_decompile_one(program, fn) for fn in functions)}
        actual = {}
        summary = decompile_functions(program, functions, threads=2, on_result=lambda result: actual.setdefault(result.addr, result.c_text))
        assert summary.completed == len(functions)
        assert summary.errored == summary.timed_out == 0
        assert actual == expected
