from __future__ import annotations

import hashlib
import json

import pytest

from agentdecompile_recovery.corpus.dashboard.binary_coverage import annotate_binary_coverage

pytestmark = pytest.mark.unit


def test_binary_coverage_keeps_capability_and_proof_separate(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "game.exe"
    binary.write_bytes(b"MZ" + b"\0" * 62)
    digest = "a" * 64
    presets = tmp_path / "presets"
    presets.mkdir()
    target = b"target object fixture"
    target_revision = hashlib.sha256(target).hexdigest()
    (presets / "target.obj").write_bytes(target)
    (presets / "game-msvc.json").write_text(json.dumps({
        "id": "game-msvc", "label": "Game MSVC", "platform": "windows-x86",
        "artifactHash": digest, "compilerScript": "cl /c {{cFilePath}} /Fo{{objFilePath}}",
        "targets": {"game_main": {"path": "target.obj", "sha256": target_revision, "symbol": "_game_main"}},
    }))
    monkeypatch.setenv("AGENT_DECOMPILE_MATCHING_PRESET_ROOT", str(presets))
    row = {
        "repo": str(binary), "kind": "binary", "sha256": digest,
        "sourcePaths": [str(binary)], "projectBindings": [{"locator": "project"}],
        "funcs": 12, "decomp": {"files": 3},
    }

    annotate_binary_coverage([row], {str(binary): digest})

    coverage = row["coverage"]
    assert coverage["exactHashRegistration"]["status"] == "confirmed"
    assert coverage["parser"] == {"status": "supported", "format": "pe", "provider": "agentdecompile.binary-inventory.v1"}
    assert coverage["projectProvider"]["status"] == "available"
    assert coverage["evidence"] == {"status": "available", "functions": 12, "sourceFiles": 3}
    assert coverage["matchingPreset"] == {
        "status": "available", "ids": ["game-msvc"],
        "presets": [{"id": "game-msvc", "label": "Game MSVC", "platform": "windows-x86",
                     "targets": [{"function": "game_main", "symbol": "_game_main", "targetRevision": target_revision}]}],
    }
    assert coverage["proof"]["phase"] == "comparison-pending"


def test_binary_coverage_reports_missing_support_without_match_claim(tmp_path) -> None:
    binary = tmp_path / "opaque.bin"
    binary.write_bytes(b"not an executable")
    row = {"repo": str(binary), "kind": "binary", "sha256": None, "funcs": 0, "decomp": {}}

    annotate_binary_coverage([row], {})

    assert row["coverage"]["exactHashRegistration"]["status"] == "unconfirmed"
    assert row["coverage"]["parser"]["status"] == "unsupported"
    assert row["coverage"]["evidence"]["status"] == "not-produced"
    assert row["coverage"]["proof"]["phase"] == "comparison-pending"


def test_unset_preset_root_does_not_scan_current_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_DECOMPILE_MATCHING_PRESET_ROOT", raising=False)
    digest = "b" * 64
    (tmp_path / "unrelated.json").write_text(json.dumps({"artifactHash": digest}))
    row = {"kind": "record", "sha256": digest, "funcs": 0, "decomp": {}}

    annotate_binary_coverage([row], {})

    assert row["coverage"]["matchingPreset"] == {"status": "unavailable", "ids": [], "presets": []}


def test_binary_coverage_rejects_old_incomplete_mismatched_preset(tmp_path, monkeypatch) -> None:
    digest = "a" * 64
    presets = tmp_path / "presets"
    presets.mkdir()
    (presets / "game.json").write_text(json.dumps({"id": "game-msvc", "artifactHash": digest}))
    monkeypatch.setenv("AGENT_DECOMPILE_MATCHING_PRESET_ROOT", str(presets))
    row = {"kind": "record", "format": "pe", "sha256": digest}

    annotate_binary_coverage([row], {})

    assert row["coverage"]["matchingPreset"] == {"status": "unavailable", "ids": [], "presets": []}
    assert row["coverage"]["proof"]["phase"] == "comparison-pending"
