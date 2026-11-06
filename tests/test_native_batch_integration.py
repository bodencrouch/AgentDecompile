"""JVM-free native batch replay against the checked-in snapshot fixture."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentdecompile_recovery.native_snapshot.differential import MATCH, classify
from agentdecompile_recovery.native_snapshot.manifest import load_manifest


FIXTURE = Path(__file__).parent / "fixtures" / "native_snapshot" / "test_x86_64"


@pytest.mark.integration
def test_checked_in_snapshot_replays_through_native_batch(tmp_path: Path, gnsdk_build_dir: Path) -> None:
    batch = gnsdk_build_dir / "tools" / "gnsdk_batch" / "gnsdk-batch"
    sleigh_home = gnsdk_build_dir / "ghidra-decomp" / "sleigh-home"
    if not batch.is_file() or not sleigh_home.is_dir():
        pytest.skip("set GNSDK_BUILD_DIR to a native SDK build to exercise gnsdk-batch")
    output = tmp_path / "results.jsonl"
    native_tmp = tmp_path / "native-tmp"
    completed = subprocess.run(
        [
            str(batch),
            "--sleigh-home",
            str(sleigh_home),
            "--snapshot",
            str(FIXTURE),
            "--output",
            str(output),
            "--timeout",
            "30",
            "--workers",
            "2",
            "--mem",
            "4G",
            "--cgroup-mem",
            "0",
            "--tmpdir",
            str(native_tmp),
        ],
        text=True, capture_output=True, timeout=40, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    native = {record["id"]: record["result"]["c"] for record in map(json.loads, output.read_text().splitlines())}
    manifest = load_manifest(FIXTURE)
    results = [classify(entry, FIXTURE, native.get(entry.addr)) for entry in manifest.ok_entries()]
    assert all(result.classification == MATCH for result in results), results
