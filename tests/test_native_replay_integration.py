"""Native-console replay of the checked-in Java snapshot fixture.

This deliberately needs an explicitly supplied native build directory: normal
Python test runs must remain useful on machines that do not build the SDK.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentdecompile_recovery.native_snapshot.differential import MATCH, classify
from agentdecompile_recovery.native_snapshot.manifest import load_manifest
from agentdecompile_recovery.native_snapshot.replay import ConsoleReplayer


FIXTURE = Path(__file__).parent / "fixtures" / "native_snapshot" / "test_x86_64"


def _native_tools() -> tuple[Path, Path] | None:
    build = os.environ.get("GNSDK_BUILD_DIR", "").strip()
    if not build:
        return None
    root = Path(build)
    console = root / "ghidra-decomp" / "decomp_console"
    sleigh_home = root / "ghidra-decomp" / "sleigh-home"
    if not console.is_file() or not sleigh_home.is_dir():
        return None
    return console, sleigh_home


@pytest.mark.integration
def test_checked_in_snapshot_replays_as_exact_native_matches() -> None:
    tools = _native_tools()
    if tools is None:
        pytest.skip("set GNSDK_BUILD_DIR to a native SDK build to exercise console replay")
    console, sleigh_home = tools
    manifest = load_manifest(FIXTURE)
    replay = ConsoleReplayer(console, sleigh_home=sleigh_home, timeout_s=30).replay_manifest(FIXTURE, manifest)
    results = [
        classify(entry, FIXTURE, replay[entry.addr].c_text, crashed=replay[entry.addr].returncode < 0)
        for entry in manifest.ok_entries()
    ]
    assert len(results) == 3
    assert all(result.classification == MATCH for result in results), results
