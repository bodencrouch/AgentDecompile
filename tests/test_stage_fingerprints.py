"""Stage fingerprint isolation for mid-run --context resume."""

from __future__ import annotations

import json

from pathlib import Path

import pytest

from agentdecompile_recovery.acquisition_bundle import build_bundle, source_record
from agentdecompile_recovery.pipeline import ACQUISITION_SENSITIVE_STAGES, RecoveryConfig, RecoveryRunner

pytestmark = pytest.mark.unit


def _runner(tmp_path: Path, **kwargs: object) -> RecoveryRunner:
    binary = tmp_path / "app.bin"
    if not binary.exists():
        binary.write_bytes(b"\x7fELF" + b"\0" * 32)
    work = tmp_path / "work"
    work.mkdir(parents=True, exist_ok=True)
    config = RecoveryConfig(
        input_path=binary,
        work_dir=work,
        resume=True,
        **kwargs,  # type: ignore[arg-type]
    )
    return RecoveryRunner(config)


def _write_bundle(tmp_path: Path, *, name: str, entity_name: str) -> Path:
    out = tmp_path / name
    target = {"stableId": "fixture", "sha256": "a" * 64, "architectureHint": "x86", "imageBase": 0x400000}
    build_bundle(
        out_dir=out,
        target=target,
        sources=[source_record(path=f"{name}.c", source_id=name, kind="source", content_hash=name, extractor="test")],
        facts=[
            {
                "name": entity_name,
                "entryOffset": 0x401000,
                "sourceId": name,
                "decompiled": f"int {entity_name}(void) {{ return 0; }}",
            }
        ],
    )
    return out


def test_early_stages_ignore_context_path_changes(tmp_path: Path) -> None:
    notes_a = tmp_path / "notes-a.md"
    notes_a.write_text("alpha\n", encoding="utf-8")
    notes_b = tmp_path / "notes-b.md"
    notes_b.write_text("beta\n", encoding="utf-8")

    before = _runner(tmp_path, context_paths=(notes_a,))
    after = _runner(tmp_path, context_paths=(notes_b,))

    for stage in before.stages:
        if stage.name in ACQUISITION_SENSITIVE_STAGES:
            continue
        assert before.stage_fingerprint(stage) == after.stage_fingerprint(stage), stage.name
        assert "acquisitionIdentity" not in before.stage_config(stage)
        assert "contextPaths" not in before.stage_config(stage)


def test_acquisition_sensitive_stages_track_bundle_identity(tmp_path: Path) -> None:
    bundle_a = _write_bundle(tmp_path, name="bundle-a", entity_name="alpha")
    bundle_b = _write_bundle(tmp_path, name="bundle-b", entity_name="beta")
    notes = tmp_path / "notes.md"
    notes.write_text("noise\n", encoding="utf-8")

    with_a = _runner(tmp_path, acquisition_bundle=bundle_a, context_paths=(notes,))
    with_b = _runner(tmp_path, acquisition_bundle=bundle_b, context_paths=(notes,))
    same_a = _runner(tmp_path, acquisition_bundle=bundle_a, context_paths=(tmp_path / "other.md",))

    for stage in with_a.stages:
        if stage.name not in ACQUISITION_SENSITIVE_STAGES:
            continue
        assert with_a.stage_fingerprint(stage) != with_b.stage_fingerprint(stage), stage.name
        # Path list noise must not invalidate when the acquired bundle is unchanged.
        assert with_a.stage_fingerprint(stage) == same_a.stage_fingerprint(stage), stage.name
        identity = with_a.stage_config(stage)["acquisitionIdentity"]
        assert identity["kind"] == "bundle"
        assert identity["factsSha256"]


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("unity_project_out", "project-out"),
        ("unity_editor", "unity-editor"),
        ("unity_editor_version", "2022.3.62f2"),
        ("unity_max_memory_gb", 8.0),
        ("unity_include_resources_assets", True),
        ("unity_repair_attempts", 2),
        ("unity_editor_timeout", 1800),
        ("unity_assetripper_cli", "assetripper"),
        ("unity_assetripper_remote_host", "root@192.0.2.10"),
        ("unity_assetripper_remote_root", "/tmp/remote-root"),
        ("unity_assetripper_remote_input", "/tmp/remote-root/input"),
        ("unity_assetripper_remote_port", 18086),
        ("unity_assetripper_ssh_host_key_alias", "100.64.0.8"),
        ("unity_only", True),
        ("unity_ilspycmd", "ilspycmd"),
        ("unity_install_mcp_bridge", True),
    ],
)
def test_changed_unity_settings_invalidate_unity_and_report_fingerprints(
    tmp_path: Path,
    setting: str,
    value: object,
) -> None:
    path_settings = {"unity_project_out", "unity_editor", "unity_assetripper_cli", "unity_ilspycmd"}
    changed_value = tmp_path / str(value) if setting in path_settings else value
    before = _runner(tmp_path)
    after = _runner(tmp_path, **{setting: changed_value})

    for stage in before.stages:
        if stage.name.startswith("unity-") or stage.name == "report":
            assert before.stage_fingerprint(stage) != after.stage_fingerprint(stage), stage.name
        elif stage.name == "discover":
            assert before.stage_fingerprint(stage) == after.stage_fingerprint(stage)


def test_resolve_facts_prefers_acquisition_bundle_over_context_paths(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path, name="acquired", entity_name="from_bundle")
    notes = tmp_path / "notes.md"
    notes.write_text("should not rebuild pack when bundle is set\n", encoding="utf-8")
    runner = _runner(tmp_path, acquisition_bundle=bundle, context_paths=(notes,))
    target = {
        "stableId": "fixture",
        "sha256": "a" * 64,
        "architectureHint": "x86",
        "imageBase": 0x400000,
        "binaryPath": str(runner.config.input_path),
    }
    facts = runner.resolve_acquisition_facts_source(target)
    assert facts is not None
    assert facts.parent == bundle
    assert not (runner.run_dir / "context-pack" / "acquisition-bundle" / "manifest.json").exists()
    binding = json.loads((runner.run_dir / "acquisition-bundle.json").read_text(encoding="utf-8"))
    assert Path(binding["bundleDir"]) == bundle
